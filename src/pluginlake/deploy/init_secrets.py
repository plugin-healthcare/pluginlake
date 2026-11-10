"""Prepare the data folder and generate the secrets of the production compose.

Runs once before the stack starts, inside the ``pluginlake-init`` image and as the host user
(``just up`` calls it). It creates the folders the containers mount, a minimal ``passwd`` file so
Postgres can start as an arbitrary uid, and one file per secret in ``secrets/`` (mode 0400).
Existing files are never overwritten, so running it again is safe.
"""

import argparse
import base64
import os
import secrets
import string
from pathlib import Path

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

FOLDERS = ("postgres", "data", "bootstrap", "prometheus", "marquez-db", "secrets")
SYMBOLS = "!#%*+-=?@^_"


def random_hex(nbytes: int = 16) -> str:
    """Return a random hex string of ``2 * nbytes`` characters."""
    return secrets.token_hex(nbytes)


def random_base64(nbytes: int = 32) -> str:
    """Return a random base64 string (at least 32 characters for 24 bytes or more)."""
    return base64.b64encode(secrets.token_bytes(nbytes)).decode()


def random_password(length: int = 24) -> str:
    """Return a password with upper case, lower case, a digit and a symbol (Zitadel policy)."""
    pools = (string.ascii_uppercase, string.ascii_lowercase, string.digits, SYMBOLS)
    chars = [secrets.choice(pool) for pool in pools]
    chars += [secrets.choice("".join(pools)) for _ in range(length - len(pools))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def build_secret_files() -> dict[str, str]:
    """Generate the content of every file in ``secrets/``.

    Postgres gets an admin password that only ``pluginlake-db-init`` uses. Every other service
    gets its own database password. Zitadel, its login UI and Marquez can only read environment
    variables, so their values are also written as env files that compose passes with ``env_file``.

    Returns:
        Mapping of file name to content.
    """
    marquez_password = random_hex()
    zitadel_db_password = random_hex()
    return {
        "postgres_password": random_hex(),
        "dagster_pg_password": random_hex(),
        "ducklake_pg_password": random_hex(),
        "postgres_exporter_password": random_hex(),
        "prometheus_remote_write_password": "",
        "marquez_db_password": marquez_password,
        "zitadel_db_password": zitadel_db_password,
        "zitadel_masterkey": random_hex(),
        "marquez.env": f"POSTGRES_PASSWORD={marquez_password}\n",
        "zitadel-login.env": f"ZITADEL_SESSION_COOKIE_SECRET={random_base64()}\n",
        "zitadel-api.env": (
            f"ZITADEL_DATABASE_POSTGRES_USER_PASSWORD={zitadel_db_password}\n"
            f"ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD={random_password()}\n"
        ),
    }


def passwd_file(uid: int, gid: int) -> str:
    """Return a minimal ``/etc/passwd`` so Postgres can start as an arbitrary host uid."""
    return f"root:x:0:0:root:/root:/sbin/nologin\npluginlake:x:{uid}:{gid}:pluginlake:/tmp:/sbin/nologin\n"


def init_home(home: Path, uid: int, gid: int) -> list[str]:
    """Create the folders, the passwd file and the missing secrets below ``home``.

    Args:
        home: The data folder (``PLUGINLAKE_HOME``), which must already exist.
        uid: User id the containers run as.
        gid: Group id the containers run as.

    Returns:
        Names of the secrets that were created.
    """
    for folder in FOLDERS:
        (home / folder).mkdir(exist_ok=True)
    (home / "bootstrap").chmod(0o700)
    (home / "secrets").chmod(0o700)

    passwd = home / "passwd"
    if not passwd.exists():
        passwd.write_text(passwd_file(uid, gid), encoding="utf-8")

    created = []
    for name, content in build_secret_files().items():
        path = home / "secrets" / name
        if path.exists():
            continue
        path.write_text(content, encoding="utf-8")
        path.chmod(0o400)
        created.append(name)
    return created


def main(argv: list[str] | None = None) -> None:
    """Entry point: ``python -m pluginlake.deploy.init_secrets <home>``."""
    parser = argparse.ArgumentParser(prog="init_secrets", description="Create the data folder and the secrets.")
    parser.add_argument("home", type=Path, help="The data folder (PLUGINLAKE_HOME).")
    home = parser.parse_args(argv).home
    created = init_home(home, os.getuid(), os.getgid())
    logger.info("Created %d secrets in %s: %s", len(created), home / "secrets", ", ".join(created) or "none")
    if "zitadel-api.env" in created:
        logger.info("The Zitadel admin password is in %s", home / "secrets" / "zitadel-api.env")


if __name__ == "__main__":
    main()
