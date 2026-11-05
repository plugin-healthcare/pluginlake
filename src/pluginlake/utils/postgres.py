"""PostgreSQL helpers shared by DuckLake and the Dagster launcher."""

import psycopg2
from psycopg2 import sql

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def ensure_database(*, host: str, port: int, user: str, password: str, dbname: str) -> bool:
    """Create the database ``dbname`` if it does not exist.

    Connects to the default ``postgres`` database with autocommit, because
    ``CREATE DATABASE`` cannot run inside a transaction.

    Args:
        host: PostgreSQL hostname.
        port: PostgreSQL port.
        user: User allowed to create databases.
        password: Password of ``user``.
        dbname: Database to create.

    Returns:
        ``True`` if the database was created, ``False`` if it already existed.
    """
    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname="postgres")
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone():
                logger.info("Database '%s' already exists.", dbname)
                return False
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            logger.info("Created database '%s'.", dbname)
            return True
    finally:
        conn.close()
