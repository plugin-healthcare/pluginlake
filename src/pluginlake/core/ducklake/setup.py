"""DuckLake database setup and connection management."""

import threading
import time
from functools import cache

import duckdb

from pluginlake.core.config import DuckLakeSettings
from pluginlake.core.storage.base import StorageBackend
from pluginlake.core.storage.local import LocalStorageBackend
from pluginlake.utils import postgres
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_ATTACH_ATTEMPTS = 3
_shared_lock = threading.Lock()


def _resolve_storage_backend(settings: DuckLakeSettings) -> StorageBackend:
    """Return a LocalStorageBackend for the given settings.

    Args:
        settings: DuckLake settings containing the data path.

    Returns:
        A local storage backend using the configured data path.
    """
    return LocalStorageBackend(settings.data_path)


def ensure_database(settings: DuckLakeSettings) -> None:
    """Create the DuckLake PostgreSQL database if it does not exist.

    Args:
        settings: DuckLake settings with PostgreSQL connection details.
    """
    postgres.ensure_database(
        host=settings.pg_host,
        port=settings.pg_port,
        user=settings.pg_user,
        password=settings.pg_password.get_secret_value(),
        dbname=settings.pg_db,
    )


def _open_connection(backend: StorageBackend, *, pg_connection_cache: bool) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection with DuckLake loaded and storage configured."""
    conn = duckdb.connect()
    conn.execute("INSTALL ducklake")
    conn.execute("LOAD ducklake")
    if not pg_connection_cache:
        # Must precede ATTACH; a connection pooled during ATTACH would otherwise go stale.
        conn.execute("SET GLOBAL pg_connection_cache = false")
    backend.configure_duckdb(conn)
    return conn


def create_connection(
    settings: DuckLakeSettings,
    backend: StorageBackend | None = None,
    *,
    pg_connection_cache: bool = True,
) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with DuckLake attached.

    Installs and loads the DuckLake extension, applies any storage-specific
    DuckDB configuration, and attaches the DuckLake catalog.

    Args:
        settings: DuckLake settings with PostgreSQL connection details.
        backend: Storage backend to use. If None, one is resolved from settings.
        pg_connection_cache: Pool the PostgreSQL metadata connections. Disable
            for long-lived connections: pooled connections break when
            PostgreSQL restarts, and each one then fails a query.

    Returns:
        A ready-to-use DuckDB connection with the ``ducklake`` catalog attached.
    """
    if backend is None:
        backend = _resolve_storage_backend(settings)

    attach_query = (
        f"ATTACH 'ducklake:postgres:{settings.pg_connection_string}' "
        f"AS ducklake (DATA_PATH '{backend.get_base_path()}', OVERRIDE_DATA_PATH TRUE)"
    )

    for attempt in range(1, _ATTACH_ATTEMPTS + 1):
        conn = _open_connection(backend, pg_connection_cache=pg_connection_cache)
        try:
            conn.execute(attach_query)
            break
        except duckdb.Error as exc:
            conn.close()
            if "already exists" not in str(exc) or attempt == _ATTACH_ATTEMPTS:
                raise
            logger.warning("DuckLake catalog init race detected (attempt %d), retrying...", attempt)
            time.sleep(1)

    _apply_tuning_options(conn, settings)

    logger.info(
        "Attached DuckLake catalog (db=%s, data_path=%s).",
        settings.pg_db,
        backend.get_base_path(),
    )
    return conn


def _sql_literal(value: str | int | bool) -> str:  # noqa: FBT001 - an option value, not a flag
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _apply_tuning_options(
    conn: duckdb.DuckDBPyConnection,
    settings: DuckLakeSettings,
) -> None:
    tuning = {
        "target_file_size": settings.target_file_size,
        "parquet_compression": settings.parquet_compression,
        "per_thread_output": settings.per_thread_output,
    }
    for option, value in tuning.items():
        if value is None:
            continue
        conn.execute(f"CALL ducklake_set_option('ducklake', '{option}', {_sql_literal(value)})")
        logger.info("DuckLake option %s = %s", option, value)


def setup_ducklake(
    settings: DuckLakeSettings | None = None,
) -> duckdb.DuckDBPyConnection:
    """Run the full DuckLake setup: ensure database exists, then connect.

    This is the main entry point called at server startup.

    Args:
        settings: DuckLake settings. Loaded from environment if None.

    Returns:
        A ready-to-use DuckDB connection with the ``ducklake`` catalog attached.
    """
    if settings is None:
        settings = DuckLakeSettings()  # type: ignore[missing-argument]

    ensure_database(settings)
    return create_connection(settings)


@cache
def _shared_connection() -> duckdb.DuckDBPyConnection:
    return create_connection(DuckLakeSettings(), pg_connection_cache=False)  # type: ignore[missing-argument]


def shared_cursor() -> duckdb.DuckDBPyConnection:
    """Return a new cursor on the process-wide DuckLake connection.

    Opening a connection loads the extension and attaches the catalog over
    PostgreSQL (~200 ms), so request handlers share one connection instead. A
    cursor shares the attached catalog, is safe to use from its own thread and
    sees tables written by other processes. Close it when done.

    Returns:
        A cursor with the ``ducklake`` catalog attached.
    """
    with _shared_lock:
        return _shared_connection().cursor()


def close_shared_connection() -> None:
    """Close the shared connection, if open; the next cursor reconnects."""
    with _shared_lock:
        if _shared_connection.cache_info().currsize:
            _shared_connection().close()
        _shared_connection.cache_clear()
