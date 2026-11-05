"""Start a Dagster process with its Postgres password from a Docker secret.

``config/dagster/dagster.yaml`` can only read the storage password from an
environment variable (``DAGSTER_PG_PASSWORD``). This launcher loads
:class:`DagsterPostgresSettings`, which pydantic fills from
``/run/secrets/dagster_pg_password``, sets ``DAGSTER_PG_PASSWORD`` for the
Dagster process only and replaces itself with the command. Other services read
their secrets through their settings classes and do not need a launcher.

The module is self-contained (stdlib and pydantic-settings only), so the
production webserver/daemon image runs it as a single file without installing
pluginlake. Only ``--ensure-db`` imports pluginlake; it is used by the dev image.

Usage::

    python -m pluginlake.deploy.dagster_env [--ensure-db] <command> [args...]
    python dagster_env.py <command> [args...]  # production image

``--ensure-db`` creates the Dagster database first if it does not exist (dev
stack; the hardened Postgres image ignores ``/docker-entrypoint-initdb.d``).
"""

import argparse
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("pluginlake.deploy.dagster_env")

PASSWORD_ENV = "DAGSTER_PG_PASSWORD"  # noqa: S105 (variable name, not a value)
SECRETS_DIR = Path("/run/secrets")


class DagsterPostgresSettings(BaseSettings):
    """Connection to the Postgres database that stores the Dagster instance.

    Uses the variables ``config/dagster/dagster.yaml`` reads (``DAGSTER_PG_*``).
    In compose the password is the Docker secret ``/run/secrets/dagster_pg_password``;
    the secrets directory is only used when it exists, like ``pluginlake.config.secrets_dir``.
    """

    model_config = SettingsConfigDict(
        env_prefix="DAGSTER_PG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        secrets_dir=SECRETS_DIR if SECRETS_DIR.is_dir() else None,
    )

    host: str = Field(default="localhost", description="Dagster PostgreSQL hostname.")
    port: int = Field(default=5432, description="Dagster PostgreSQL port.")
    user: str = Field(description="Dagster PostgreSQL user.")
    password: SecretStr = Field(description="Dagster PostgreSQL password.")
    db: str = Field(default="dagster", description="Dagster PostgreSQL database name.")


def dagster_environ(settings: DagsterPostgresSettings, environ: Mapping[str, str]) -> dict[str, str]:
    """Return ``environ`` with the variable ``dagster.yaml`` reads the password from.

    Args:
        settings: Dagster Postgres settings, with the password from the secret.
        environ: The current environment.

    Returns:
        A copy of ``environ`` with ``DAGSTER_PG_PASSWORD`` set.
    """
    return {**environ, PASSWORD_ENV: settings.password.get_secret_value()}


def ensure_dagster_database(settings: DagsterPostgresSettings) -> None:
    """Create the Dagster database if it does not exist yet.

    Requires pluginlake to be installed (dev image only).
    """
    from pluginlake.utils import postgres  # noqa: PLC0415 (keeps the launcher standalone in the prod image)

    postgres.ensure_database(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password.get_secret_value(),
        dbname=settings.db,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the command with the Dagster Postgres password in its environment.

    Args:
        argv: Arguments; defaults to ``sys.argv[1:]``.

    Returns:
        A non-zero exit code on error; on success the process is replaced.
    """
    parser = argparse.ArgumentParser(prog="dagster_env", description="Run a command with DAGSTER_PG_PASSWORD set.")
    parser.add_argument("--ensure-db", action="store_true", help="Create the Dagster database if missing.")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run.")
    args = parser.parse_args(argv)
    if not args.command:
        parser.error("no command given")

    try:
        settings = DagsterPostgresSettings()  # type: ignore[missing-argument]
    except ValidationError as exc:
        missing = ", ".join(f"DAGSTER_PG_{'_'.join(map(str, e['loc'])).upper()}" for e in exc.errors())
        logger.error("Dagster Postgres settings incomplete: %s", missing)  # noqa: TRY400
        return 1

    if args.ensure_db:
        ensure_dagster_database(settings)

    os.execvpe(args.command[0], args.command, dagster_environ(settings, os.environ))  # noqa: S606
    return 1


if __name__ == "__main__":
    sys.exit(main())
