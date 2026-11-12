"""``pluginlake setup``: prepare a node before its compose stack starts.

Compose reads the host user, the data folder and the domain while it parses the file, so they must exist before any
container runs. This step reads ``pluginlake.toml``, creates the folders and the missing secrets (see ``secrets.toml``)
and writes ``compose.env`` for ``docker compose --env-file``. It runs as the host user, normally inside the pluginlake
image (``just setup``). With ``--dev`` it fills the development defaults and also writes the plain secrets to a
readable ``secrets.env``.
"""

import os
from pathlib import Path

from pluginlake.deploy.config import NodeSettings, load_init_config, load_station_config
from pluginlake.deploy.init_secrets import init_home
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

DEV_DOMAIN = "pluginlake.localhost"
COMPOSE_ENV = "compose.env"
DEV_SECRETS_ENV = "secrets.env"


def resolve_node(node: NodeSettings, *, dev: bool) -> NodeSettings:
    """Apply the development defaults, or require a domain.

    Args:
        node: The ``[node]`` section of ``pluginlake.toml``.
        dev: Whether the node is a development node.

    Returns:
        Settings with a domain.

    Raises:
        ValueError: If no domain is configured outside development.
    """
    if dev:
        return node.model_copy(update={"domain": node.domain or DEV_DOMAIN, "insecure_tls": True})
    if node.domain is None:
        msg = "[node] domain is required in pluginlake.toml (use --dev for pluginlake.localhost)."
        raise ValueError(msg)
    return node


def compose_env(node: NodeSettings, *, uid: int, gid: int, host_home: Path) -> str:
    """Render the values compose needs at parse time as a dotenv file.

    Args:
        node: Resolved node settings.
        uid: User id the containers run as.
        gid: Group id the containers run as.
        host_home: The data folder as the Docker host sees it.

    Returns:
        Content of ``compose.env``.
    """
    values = {
        "PLUGINLAKE_UID": str(uid),
        "PLUGINLAKE_GID": str(gid),
        "PLUGINLAKE_HOME": str(host_home),
        "PLUGINLAKE_DOMAIN": node.domain,
        "OAUTH2_PROXY_INSECURE_TLS": str(node.insecure_tls).lower(),
        "ZITADEL_ADMIN_USERNAME": node.admin_username,
    }
    return "".join(f"{key}='{value}'\n" for key, value in values.items())


def _dev_secrets_env(secrets_dir: Path) -> str:
    """Return the secrets that are plain values as ``NAME=value`` lines, for development."""
    config = load_init_config()
    lines = [
        f"{spec.name.upper()}='{(secrets_dir / spec.name).read_text(encoding='utf-8')}'\n"
        for spec in config.secrets
        if spec.template is None
    ]
    return "".join(lines)


def run_setup(config_path: Path, home: Path, host_home: Path | None = None, *, dev: bool = False) -> int:
    """Prepare ``home`` for ``docker compose``.

    Args:
        config_path: Path to ``pluginlake.toml``.
        home: The data folder, which must exist.
        host_home: The same folder as the Docker host sees it, when this runs in a container.
        dev: Use the development defaults and write ``secrets.env``.

    Returns:
        Process exit code.
    """
    try:
        node = resolve_node(load_station_config(config_path).node, dev=dev)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Invalid station config: %s", exc)  # noqa: TRY400 (a traceback adds nothing)
        return 1

    uid, gid = os.getuid(), os.getgid()
    created = init_home(home, uid, gid)
    logger.info("Created %d secrets in %s: %s", len(created), home, ", ".join(created) or "none")

    env_file = home / COMPOSE_ENV
    env_file.write_text(compose_env(node, uid=uid, gid=gid, host_home=host_home or home.resolve()), encoding="utf-8")
    env_file.chmod(0o600)
    logger.info("Wrote %s", env_file)

    if dev:
        dev_secrets = home / DEV_SECRETS_ENV
        dev_secrets.write_text(_dev_secrets_env(home / load_init_config().secrets_folder), encoding="utf-8")
        dev_secrets.chmod(0o600)
        logger.info("Development secrets are in %s", dev_secrets)
    return 0
