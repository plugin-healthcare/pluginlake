"""``pluginlake setup``: prepare a node before its compose stack starts.

Compose reads the host user, the data folder and the domain while it parses the file, so they must exist before any
container runs. This step reads ``pluginlake.toml``, creates the folders and the missing secrets (see ``secrets.toml``)
and writes ``compose.env`` for ``docker compose --env-file``. It runs as the host user, normally inside the pluginlake
image (``just setup``). A domain below ``.localhost`` is a local node: it is served with an mkcert certificate that
``just setup`` creates.
"""

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pluginlake.deploy.config import NodeSettings, StationConfig, load_station_config
from pluginlake.deploy.init_secrets import init_home, templates_revision
from pluginlake.deploy.routes import render_routes
from pluginlake.utils.logger import get_logger
from pluginlake.utils.secrets import replace_secret

logger = get_logger(__name__)

COMPOSE_ENV = "compose.env"
TLS_DIR = "tls"
TLS_CERT, TLS_KEY = "cert.pem", "key.pem"
TLS_CERT_DOMAIN = "cert.domain"
CA_DIR, CA_FILE = "ca", "ca.pem"
TLS_FILE_CONFIG = "tls.yaml"
CONTAINER_CA_DIR = "/ca"
CONTAINER_TLS_DIR = "/tls"
ROUTES_DIR = "traefik"
ROUTES_FILE = "routes.yaml"
SETUP_LOCK = ".setup.lock"


@contextmanager
def setup_lock(home: Path) -> Iterator[None]:
    """Hold an exclusive lock on ``home``, so concurrent setup runs do not interleave.

    ``just setup`` takes the same lock while it creates the local certificate.
    """
    with (home / SETUP_LOCK).open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _write_in_place(path: Path, content: str) -> None:
    """Write ``path`` only when its content changes, keeping the same file.

    Traefik mounts these files one by one, and a bind mount of a single file keeps showing the old file once it is
    replaced, so they are overwritten in place.
    """
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def is_local(domain: str) -> bool:
    """Whether ``domain`` is a local node, which browsers resolve to the local machine."""
    return domain == "localhost" or domain.endswith(".localhost")


def require_domain(node: NodeSettings) -> str:
    """Return the configured domain.

    Raises:
        ValueError: If ``[node] domain`` is not set.
    """
    if node.domain is None:
        msg = "[node] domain is required in pluginlake.toml (use pluginlake.localhost for a local node)."
        raise ValueError(msg)
    return node.domain


def tls_file_config(*, local: bool) -> str:
    """Render the Traefik file-provider config for the node certificate.

    Args:
        local: Whether the node is local, which serves the mkcert certificate.

    Returns:
        YAML for ``tls/tls.yaml``. For other domains it is empty, so Traefik uses what the operator
        configures in its static config.
    """
    if not local:
        return "{}\n"
    return f"tls:\n  certificates:\n    - certFile: {CONTAINER_TLS_DIR}/{TLS_CERT}\n      keyFile: {CONTAINER_TLS_DIR}/{TLS_KEY}\n"


def compose_env(
    node: NodeSettings,
    config: StationConfig,
    *,
    owner: tuple[int, int],
    host_home: Path,
    secrets_revision: str,
) -> str:
    """Render the values compose needs at parse time as a dotenv file.

    Args:
        node: Resolved node settings.
        config: The station config, for the lineage namespace and Prometheus settings.
        owner: User id and group id the containers run as.
        host_home: The data folder as the Docker host sees it.
        secrets_revision: Hash of the template secrets, see ``templates_revision``.

    Returns:
        Content of ``compose.env``.
    """
    values = {
        "PLUGINLAKE_UID": str(owner[0]),
        "PLUGINLAKE_GID": str(owner[1]),
        "PLUGINLAKE_HOME": str(host_home),
        "PLUGINLAKE_DOMAIN": node.domain,
        "OAUTH2_PROXY_SSL_CERT_FILE": f"{CONTAINER_CA_DIR}/{CA_FILE}" if is_local(node.domain or "") else "",
        "ZITADEL_ADMIN_USERNAME": node.admin_username,
        "PLUGINLAKE_LINEAGE_NAMESPACE": config.station.lineage_namespace,
        "PROMETHEUS_STATION_ID": config.monitoring.station_id,
        "PROMETHEUS_SCRAPE_CADVISOR": str(config.monitoring.cadvisor).lower(),
        "CADVISOR_REPLICAS": "1" if config.monitoring.cadvisor else "0",
        "PROMETHEUS_RETENTION": config.monitoring.retention,
        "PROMETHEUS_PUBLISH": config.monitoring.publish or "127.0.0.1:9090",
        "PLUGINLAKE_SECRETS_REVISION": secrets_revision,
    }
    return "".join(f"{key}='{value}'\n" for key, value in values.items())


def prepare_tls(home: Path, domain: str) -> bool:
    """Create the ``tls`` folder and its Traefik config.

    For a local node the mkcert files (``cert.pem`` and ``key.pem`` in ``tls``, ``ca.pem`` in ``ca``, all written by
    ``just setup``) must exist, and ``tls/cert.domain`` must name ``domain``.
    For other domains an existing ``tls.yaml`` is the operator's own and stays as it is.

    Args:
        home: The data folder.
        domain: Base domain of the node.

    Returns:
        False if the certificate of a local node is missing or made for another domain.
    """
    local = is_local(domain)
    tls_dir = home / TLS_DIR
    tls_dir.mkdir(mode=0o700, exist_ok=True)
    if local:
        expected = [tls_dir / TLS_CERT, tls_dir / TLS_KEY, home / CA_DIR / CA_FILE]
        missing = [str(path) for path in expected if not path.is_file()]
        if missing:
            logger.error("Missing %s: run `just setup`, which creates them with mkcert.", missing)
            return False
        cert_domain = tls_dir / TLS_CERT_DOMAIN
        if not cert_domain.is_file() or cert_domain.read_text(encoding="utf-8").strip() != domain:
            logger.error("The certificate in %s is not made for %s: run `just setup` again.", tls_dir, domain)
            return False
    config_file = tls_dir / TLS_FILE_CONFIG
    # A config left from a local node must not outlive a move to a real domain.
    own = config_file.exists() and config_file.read_text(encoding="utf-8") != tls_file_config(local=True)
    if local or not own:
        _write_in_place(config_file, tls_file_config(local=local))
    return True


def write_routes(home: Path, domain: str) -> Path:
    """Write the Traefik routing for ``domain`` below the data folder.

    Args:
        home: The data folder.
        domain: Base domain of the node.

    Returns:
        Path of the written file.
    """
    routes_dir = home / ROUTES_DIR
    routes_dir.mkdir(mode=0o700, exist_ok=True)
    routes_file = routes_dir / ROUTES_FILE
    _write_in_place(routes_file, render_routes(domain))
    return routes_file


def run_setup(config_path: Path, home: Path, host_home: Path | None = None) -> int:
    """Prepare ``home`` for ``docker compose``.

    Args:
        config_path: Path to ``pluginlake.toml``.
        home: The data folder, which must exist.
        host_home: The same folder as the Docker host sees it, when this runs in a container.

    Returns:
        Process exit code.
    """
    try:
        station = load_station_config(config_path)
        domain = require_domain(station.node)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Invalid station config: %s", exc)  # noqa: TRY400 (a traceback adds nothing)
        return 1

    with setup_lock(home):
        return _prepare_home(station, domain, home, host_home)


def _prepare_home(station: StationConfig, domain: str, home: Path, host_home: Path | None) -> int:
    uid, gid = os.getuid(), os.getgid()
    created = init_home(home, uid, gid)
    logger.info("Created %d secrets in %s: %s", len(created), home, ", ".join(created) or "none")

    if not prepare_tls(home, domain):
        return 1

    logger.info("Wrote %s", write_routes(home, domain))

    env_file = home / COMPOSE_ENV
    env = compose_env(
        station.node,
        station,
        owner=(uid, gid),
        host_home=host_home or home.resolve(),
        secrets_revision=templates_revision(home),
    )
    replace_secret(env_file, env, mode=0o600)
    logger.info("Wrote %s", env_file)
    return 0
