"""DuckLake database setup and connection management."""

import duckdb
import psycopg2
from psycopg2 import sql

from pluginlake.core.ducklake.config import DuckLakeSettings
from pluginlake.core.storage.base import StorageBackend
from pluginlake.core.storage.local import LocalStorageBackend
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def _resolve_storage_backend(settings: DuckLakeSettings) -> StorageBackend:
    """Return a storage backend instance based on the configured backend type.

    Args:
        settings: DuckLake settings containing the backend type and data path.

    Raises:
        ValueError: If the configured storage backend is not supported.
    """
    backend = settings.storage_backend.lower()
    if backend == "local":
        return LocalStorageBackend(settings.data_path)
    msg = f"Unsupported storage backend: {backend!r}. Supported: 'local'."
    raise ValueError(msg)


def ensure_database(settings: DuckLakeSettings) -> None:
    """Create the DuckLake PostgreSQL database if it does not exist.

    Connects to the default ``postgres`` database to check for and
    optionally create the target database. Uses autocommit because
    CREATE DATABASE cannot run inside a transaction.

    Args:
        settings: DuckLake settings with PostgreSQL connection details.
    """
    conn = psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        user=settings.pg_user,
        password=settings.pg_password,
        dbname="postgres",
    )
    conn.autocommit = True

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (settings.pg_db,),
            )
            if cur.fetchone():
                logger.info("DuckLake database '%s' already exists.", settings.pg_db)
                return

            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.pg_db)))
            logger.info("Created DuckLake database '%s'.", settings.pg_db)
    finally:
        conn.close()


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
        f"AS ducklake (DATA_PATH '{backend.get_base_path()}')"
    )
    conn.execute(attach_query)

    logger.info(
        "Attached DuckLake catalog (db=%s, data_path=%s).",
        settings.pg_db,
        backend.get_base_path(),
    )
    return conn


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
        settings = DuckLakeSettings()

    ensure_database(settings)
    backend = _resolve_storage_backend(settings)
    return create_connection(settings, backend)
