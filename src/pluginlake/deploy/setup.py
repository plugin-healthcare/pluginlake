"""``pluginlake setup``: prepare a node before its compose stack starts.

Compose reads the host user, the data folder and the domain while it parses the file, so they must exist before any
container runs. This step reads ``pluginlake.toml``, creates the folders and the missing secrets (see ``secrets.toml``)
and writes ``compose.env`` for ``docker compose --env-file``. It runs as the host user, normally inside the pluginlake
image (``just setup``). With ``--dev`` it fills the development defaults and also writes the plain secrets to a
readable ``secrets.env``.
"""

import os
from pathlib import Path

from pluginlake.deploy.config import NodeSettings, StationConfig, load_init_config, load_station_config
from pluginlake.deploy.init_secrets import init_home
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

DEV_DOMAIN = "pluginlake.localhost"
COMPOSE_ENV = "compose.env"
TLS_DIR = "tls"
TLS_CERT, TLS_KEY, TLS_CA = "cert.pem", "key.pem", "ca.pem"
TLS_FILE_CONFIG = "tls.yaml"
CONTAINER_TLS_DIR = "/tls"
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
        return node.model_copy(update={"domain": node.domain or DEV_DOMAIN})
    if node.domain is None:
        msg = "[node] domain is required in pluginlake.toml (use --dev for pluginlake.localhost)."
        raise ValueError(msg)
    return node


def tls_file_config(*, dev: bool) -> str:
    """Render the Traefik file-provider config for the node certificate.

    Args:
        dev: Whether the node is a development node, which serves the mkcert certificate.

    Returns:
        YAML for ``tls/tls.yaml``. Outside development it is empty, so Traefik uses what the operator
        configures in its static config.
    """
    if not dev:
        return "{}\n"
    return f"tls:\n  certificates:\n    - certFile: {CONTAINER_TLS_DIR}/{TLS_CERT}\n      keyFile: {CONTAINER_TLS_DIR}/{TLS_KEY}\n"


def compose_env(
    node: NodeSettings,
    config: StationConfig,
    *,
    owner: tuple[int, int],
    host_home: Path,
    dev: bool = False,
) -> str:
    """Render the values compose needs at parse time as a dotenv file.

    Args:
        node: Resolved node settings.
        config: The station config, for the lineage namespace and Prometheus settings.
        owner: User id and group id the containers run as.
        host_home: The data folder as the Docker host sees it.
        dev: Trust the mkcert root CA in oauth2-proxy.

    Returns:
        Content of ``compose.env``.
    """
    values = {
        "PLUGINLAKE_UID": str(owner[0]),
        "PLUGINLAKE_GID": str(owner[1]),
        "PLUGINLAKE_HOME": str(host_home),
        "PLUGINLAKE_DOMAIN": node.domain,
        "OAUTH2_PROXY_SSL_CERT_FILE": f"{CONTAINER_TLS_DIR}/{TLS_CA}" if dev else "",
        "ZITADEL_ADMIN_USERNAME": node.admin_username,
        "PLUGINLAKE_LINEAGE_NAMESPACE": config.station.lineage_namespace,
        "PROMETHEUS_STATION_ID": config.monitoring.station_id,
        "PROMETHEUS_SCRAPE_CADVISOR": str(config.monitoring.cadvisor).lower(),
        "PROMETHEUS_REMOTE_WRITE_URL": config.monitoring.remote_write_url or "",
    }
    return "".join(f"{key}='{value}'\n" for key, value in values.items())


def prepare_tls(home: Path, *, dev: bool) -> bool:
    """Create the ``tls`` folder and its Traefik config.

    In development the mkcert files (``cert.pem``, ``key.pem``, ``ca.pem``, written by ``just setup --dev``) must exist.
    Outside development an existing ``tls.yaml`` is the operator's own and stays as it is.

    Args:
        home: The data folder.
        dev: Whether the node is a development node.

    Returns:
        False if a development certificate is missing.
    """
    tls_dir = home / TLS_DIR
    tls_dir.mkdir(mode=0o700, exist_ok=True)
    if dev:
        missing = [name for name in (TLS_CERT, TLS_KEY, TLS_CA) if not (tls_dir / name).is_file()]
        if missing:
            logger.error("Missing %s in %s: run `just setup --dev`, which creates them with mkcert.", missing, tls_dir)
            return False
    config_file = tls_dir / TLS_FILE_CONFIG
    if dev or not config_file.exists():
        config_file.write_text(tls_file_config(dev=dev), encoding="utf-8")
    return True


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
        station = load_station_config(config_path)
        node = resolve_node(station.node, dev=dev)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Invalid station config: %s", exc)  # noqa: TRY400 (a traceback adds nothing)
        return 1

    uid, gid = os.getuid(), os.getgid()
    created = init_home(home, uid, gid)
    logger.info("Created %d secrets in %s: %s", len(created), home, ", ".join(created) or "none")

    if not prepare_tls(home, dev=dev):
        return 1

    env_file = home / COMPOSE_ENV
    env = compose_env(
        node,
        station,
        owner=(uid, gid),
        host_home=host_home or home.resolve(),
        dev=dev,
    )
    env_file.write_text(env, encoding="utf-8")
    env_file.chmod(0o600)
    logger.info("Wrote %s", env_file)

    if dev:
        dev_secrets = home / DEV_SECRETS_ENV
        dev_secrets.write_text(_dev_secrets_env(home / load_init_config().secrets_folder), encoding="utf-8")
        dev_secrets.chmod(0o600)
        logger.info("Development secrets are in %s", dev_secrets)
    return 0
