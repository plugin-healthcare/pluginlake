"""Create the data folder layout and the secrets of the production compose.

Used by ``pluginlake setup``. It creates the folders the containers mount, a minimal ``passwd`` file so Postgres can
start as an arbitrary uid, and one file per secret listed in ``secrets.toml`` (mode 0400).
Generated secrets are never overwritten, so running it again is safe.
Template secrets are rendered again on every run, so they always hold the current value of the secrets they refer to.
"""

import fcntl
import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pluginlake.deploy.config import InitConfig, SecretKind, load_init_config
from pluginlake.utils.logger import get_logger
from pluginlake.utils.secrets import random_base64, random_hex, random_password, replace_secret, write_secret

logger = get_logger(__name__)


GENERATORS = {
    SecretKind.HEX: random_hex,
    SecretKind.BASE64: random_base64,
    SecretKind.PASSWORD: random_password,
    SecretKind.EMPTY: str,
}


def build_secret_files(config: InitConfig, existing: dict[str, str] | None = None) -> dict[str, str]:
    """Generate the content of every secret in ``config``.

    Secrets that already exist keep their value.
    Templates are always rendered from the current values, so they stay consistent with the secrets they refer to.

    Args:
        config: The secrets to generate.
        existing: Current content of the secret files, by name.

    Returns:
        Mapping of file name to content.
    """
    values = dict(existing or {})
    for spec in config.secrets:
        if spec.kind is SecretKind.TEMPLATE:
            quoted = {name: json.dumps(values[name]) for name in spec.references}
            values[spec.name] = (spec.template or "").format(**quoted)
        elif spec.name not in values:
            values[spec.name] = GENERATORS[spec.kind]()
    return {spec.name: values[spec.name] for spec in config.secrets}


def passwd_file(uid: int, gid: int) -> str:
    """Return a minimal ``/etc/passwd`` so Postgres can start as an arbitrary host uid."""
    return f"root:x:0:0:root:/root:/sbin/nologin\npluginlake:x:{uid}:{gid}:pluginlake:/tmp:/sbin/nologin\n"


@contextmanager
def _exclusive(lock_file: Path) -> Iterator[None]:
    """Hold an exclusive lock on ``lock_file``, so concurrent setup runs on one home do not interleave."""
    with lock_file.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def init_home(home: Path, uid: int, gid: int, config: InitConfig | None = None) -> list[str]:
    """Create the folders, the passwd file and the missing secrets below ``home``.

    Args:
        home: The data folder (``PLUGINLAKE_HOME``), which must already exist.
        uid: User id the containers run as.
        gid: Group id the containers run as.
        config: Folders and secrets to create; defaults to the ``secrets.toml`` shipped with pluginlake.

    Returns:
        Names of the secrets that were created, and of the templates that were rendered again.
    """
    config = config or load_init_config()
    secrets = home / config.secrets_folder
    for folder in config.folders:
        (home / folder).mkdir(parents=True, exist_ok=True)
    for folder in [*config.private_folders, config.secrets_folder]:
        (home / folder).mkdir(parents=True, exist_ok=True)
        (home / folder).chmod(0o700)

    passwd = home / "passwd"
    if not passwd.exists():
        passwd.write_text(passwd_file(uid, gid), encoding="utf-8")

    with _exclusive(home / ".setup.lock"):
        existing = {
            # Stripped like `pluginlake-db-init` does, so a template holds the password the role gets.
            spec.name: (secrets / spec.name).read_text(encoding="utf-8").strip()
            for spec in config.secrets
            if spec.kind is not SecretKind.TEMPLATE and (secrets / spec.name).exists()
        }
        files = build_secret_files(config, existing)
        written = []
        for spec in config.secrets:
            write = replace_secret if spec.kind is SecretKind.TEMPLATE else write_secret
            if write(secrets / spec.name, files[spec.name]):
                written.append(spec.name)
        return written


def templates_revision(home: Path, config: InitConfig | None = None) -> str:
    """Return a short hash of the rendered template secrets below ``home``.

    Compose does not notice a changed file inside a mount, so the containers that read the templates get this value
    in their environment, and a changed template makes compose recreate them.

    Args:
        home: The data folder, after ``init_home`` ran.
        config: The secrets; defaults to the ``secrets.toml`` shipped with pluginlake.

    Returns:
        The first 16 hex characters of the SHA-256 over the templates.
    """
    config = config or load_init_config()
    digest = hashlib.sha256()
    for spec in config.secrets:
        if spec.kind is SecretKind.TEMPLATE:
            digest.update((home / config.secrets_folder / spec.name).read_bytes())
    return digest.hexdigest()[:16]
