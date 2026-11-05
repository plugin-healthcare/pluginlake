"""DuckLake database setup and connection management."""

import time

import duckdb

from pluginlake.core.config import DuckLakeSettings
from pluginlake.core.storage.base import StorageBackend
from pluginlake.core.storage.local import LocalStorageBackend
from pluginlake.utils import postgres
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


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


def create_connection(
    settings: DuckLakeSettings,
    backend: StorageBackend | None = None,
) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with DuckLake attached.

    Installs and loads the DuckLake extension, applies any storage-specific
    DuckDB configuration, and attaches the DuckLake catalog.

    Args:
        settings: DuckLake settings with PostgreSQL connection details.
        backend: Storage backend to use. If None, one is resolved from settings.

    Returns:
        A ready-to-use DuckDB connection with the ``ducklake`` catalog attached.
    """
    if backend is None:
        backend = _resolve_storage_backend(settings)

    conn = duckdb.connect()

    conn.execute("INSTALL ducklake")
    conn.execute("LOAD ducklake")

    backend.configure_duckdb(conn)

    attach_query = (
        f"ATTACH 'ducklake:postgres:{settings.pg_connection_string}' "
        f"AS ducklake (DATA_PATH '{backend.get_base_path()}', OVERRIDE_DATA_PATH TRUE)"
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn.execute(attach_query)
            break
        except duckdb.Error as exc:
            if "already exists" in str(exc) and attempt < max_retries - 1:
                logger.warning("DuckLake catalog init race detected (attempt %d), retrying...", attempt + 1)
                time.sleep(1)
                conn.close()
                conn = duckdb.connect()
                conn.execute("INSTALL ducklake")
                conn.execute("LOAD ducklake")
                backend.configure_duckdb(conn)
            else:
                raise

    _apply_tuning_options(conn, settings)

    logger.info(
        "Attached DuckLake catalog (db=%s, data_path=%s).",
        settings.pg_db,
        backend.get_base_path(),
    )
    return conn


def _apply_tuning_options(
    conn: duckdb.DuckDBPyConnection,
    settings: DuckLakeSettings,
) -> None:
    tuning: list[tuple[str, int | str | bool]] = []
    if settings.target_file_size is not None:
        tuning.append(("target_file_size", settings.target_file_size))
    if settings.parquet_compression is not None:
        tuning.append(("parquet_compression", settings.parquet_compression))
    if settings.per_thread_output is not None:
        tuning.append(("per_thread_output", settings.per_thread_output))

    for option, value in tuning:
        if isinstance(value, str):
            sql_value = f"'{value}'"
        elif isinstance(value, bool):
            sql_value = str(value).lower()
        else:
            sql_value = str(value)
        conn.execute(f"CALL ducklake_set_option('ducklake', '{option}', {sql_value})")
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
    backend = _resolve_storage_backend(settings)
    return create_connection(settings, backend)
