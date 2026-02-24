"""DuckLake database setup and connection management."""

from pathlib import Path

import duckdb
import psycopg2
from psycopg2 import sql

from pluginlake.core.config import DuckLakeSettings
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


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
) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with DuckLake attached.

    Installs and loads the DuckLake extension, ensures the data
    directory exists, and attaches the DuckLake catalog.

    Args:
        settings: DuckLake settings with PostgreSQL connection details.

    Returns:
        A ready-to-use DuckDB connection with the ``ducklake`` catalog attached.
    """
    data_path = Path(settings.data_path)
    if not data_path.is_absolute():
        # Resolve relative paths from the project root
        project_root = Path(__file__).resolve().parents[4]
        data_path = project_root / data_path
    data_path = data_path.resolve()
    data_path.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect()

    conn.execute("INSTALL ducklake")
    conn.execute("LOAD ducklake")

    attach_query = f"ATTACH 'ducklake:postgres:{settings.pg_connection_string}' AS ducklake (DATA_PATH '{data_path}')"
    conn.execute(attach_query)

    logger.info(
        "Attached DuckLake catalog (db=%s, data_path=%s).",
        settings.pg_db,
        data_path,
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
        settings = DuckLakeSettings()  # type: ignore[call-arg]  # pydantic-settings loads from env

    ensure_database(settings)
    return create_connection(settings)
