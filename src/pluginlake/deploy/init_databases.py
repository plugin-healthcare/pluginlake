r"""Create the database roles and databases of the production compose.

Runs as the ``pluginlake-db-init`` service after Postgres is healthy. It is the only service that
uses the Postgres superuser besides Postgres itself. Each other service then gets its own role with
its own generated password, limited to its own database.

Usage::

    python -m pluginlake.deploy.init_databases --host postgres --port 5432 \\
        --admin-user admin --admin-password-file /run/secrets/postgres_password \\
        --role dagster:dagster:/run/secrets/dagster_pg_password \\
        --role monitoring::/run/secrets/postgres_exporter_password

A role spec is ``user:database:password_file``. An empty database makes the role a read-only
monitoring role (member of ``pg_monitor``). The command is idempotent and resets the password of
existing roles to the current secret.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg2
from psycopg2 import sql

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

ROLE_PARTS = 3


@dataclass(frozen=True)
class RoleSpec:
    """A role with its optional own database."""

    user: str
    database: str
    password: str


def parse_role(spec: str) -> RoleSpec:
    """Parse ``user:database:password_file`` and read the password file.

    Args:
        spec: The role specification.

    Returns:
        The parsed role with its password.

    Raises:
        ValueError: If the spec does not have three parts or the user is empty.
    """
    parts = spec.split(":")
    if len(parts) != ROLE_PARTS or not parts[0]:
        msg = f"role must be user:database:password_file, got {spec!r}"
        raise ValueError(msg)
    user, database, password_file = parts
    return RoleSpec(user, database, Path(password_file).read_text(encoding="utf-8").strip())


def ensure_role(cur: psycopg2.extensions.cursor, role: RoleSpec) -> None:
    """Create ``role`` (or reset its password), its database and its privileges."""
    user = sql.Identifier(role.user)
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role.user,))
    verb = "ALTER" if cur.fetchone() else "CREATE"
    cur.execute(sql.SQL(f"{verb} ROLE {{}} LOGIN PASSWORD %s").format(user), (role.password,))

    if not role.database:
        cur.execute(sql.SQL("GRANT pg_monitor TO {}").format(user))
        logger.info("Role '%s' is a monitoring role.", role.user)
        return

    database = sql.Identifier(role.database)
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (role.database,))
    if not cur.fetchone():
        cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(database, user))
    cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(database))
    cur.execute(sql.SQL("GRANT ALL ON DATABASE {} TO {}").format(database, user))
    logger.info("Role '%s' owns database '%s'.", role.user, role.database)


def main(argv: list[str] | None = None) -> int:
    """Create every role given with ``--role``."""
    parser = argparse.ArgumentParser(prog="init_databases", description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--admin-user", required=True)
    parser.add_argument("--admin-password-file", required=True, type=Path)
    parser.add_argument("--role", action="append", required=True, type=parse_role)
    args = parser.parse_args(argv)

    conn = psycopg2.connect(
        host=args.host,
        port=args.port,
        user=args.admin_user,
        password=args.admin_password_file.read_text(encoding="utf-8").strip(),
        dbname="postgres",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for role in args.role:
                ensure_role(cur, role)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
