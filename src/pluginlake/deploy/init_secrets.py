"""Create the data folder layout and the secrets of the production compose.

Used by ``pluginlake setup``. It creates the folders the containers mount, a minimal ``passwd`` file so Postgres can
start as an arbitrary uid, and one file per secret listed in ``secrets.toml`` (mode 0400).
Existing files are never overwritten, so running it again is safe.
"""

import json
from pathlib import Path

from pluginlake.deploy.config import InitConfig, SecretKind, load_init_config
from pluginlake.utils.logger import get_logger
from pluginlake.utils.secrets import random_base64, random_hex, random_password, write_secret

logger = get_logger(__name__)


GENERATORS = {
    SecretKind.HEX: random_hex,
    SecretKind.BASE64: random_base64,
    SecretKind.PASSWORD: random_password,
    SecretKind.EMPTY: str,
}


def build_secret_files(config: InitConfig, existing: dict[str, str] | None = None) -> dict[str, str]:
    """Generate the content of every secret in ``config``.

    Secrets that already exist keep their value, so templates stay consistent with the secrets they refer to.

    Args:
        config: The secrets to generate.
        existing: Current content of the secret files, by name.

    Returns:
        Mapping of file name to content.
    """
    values = dict(existing or {})
    for spec in config.secrets:
        if spec.name in values:
            continue
        if spec.kind is SecretKind.TEMPLATE:
            quoted = {name: json.dumps(values[name]) for name in spec.references}
            values[spec.name] = (spec.template or "").format(**quoted)
        else:
            values[spec.name] = GENERATORS[spec.kind]()
    return {spec.name: values[spec.name] for spec in config.secrets}


def passwd_file(uid: int, gid: int) -> str:
    """Return a minimal ``/etc/passwd`` so Postgres can start as an arbitrary host uid."""
    return f"root:x:0:0:root:/root:/sbin/nologin\npluginlake:x:{uid}:{gid}:pluginlake:/tmp:/sbin/nologin\n"


def init_home(home: Path, uid: int, gid: int, config: InitConfig | None = None) -> list[str]:
    """Create the folders, the passwd file and the missing secrets below ``home``.

    Args:
        home: The data folder (``PLUGINLAKE_HOME``), which must already exist.
        uid: User id the containers run as.
        gid: Group id the containers run as.
        config: Folders and secrets to create; defaults to the ``secrets.toml`` shipped with pluginlake.

    Returns:
        Names of the secrets that were created.
    """
    config = config or load_init_config()
    secrets = home / config.secrets_folder
    for folder in config.folders:
        (home / folder).mkdir(exist_ok=True)
    for folder in [*config.private_folders, config.secrets_folder]:
        (home / folder).mkdir(exist_ok=True)
        (home / folder).chmod(0o700)

    passwd = home / "passwd"
    if not passwd.exists():
        passwd.write_text(passwd_file(uid, gid), encoding="utf-8")

    existing = {
        spec.name: (secrets / spec.name).read_text(encoding="utf-8")
        for spec in config.secrets
        if (secrets / spec.name).exists()
    }
    return [
        name for name, content in build_secret_files(config, existing).items() if write_secret(secrets / name, content)
    ]
