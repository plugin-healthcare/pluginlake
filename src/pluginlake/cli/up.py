"""``pluginlake up`` / ``pluginlake down`` — config-driven stack deployment.

Reads a ``pluginlake.toml`` station config and drives one of two compose stacks:

- Production (default): the stack shipped inside the package
  (``pluginlake/deploy/stack``), so no source checkout is needed. It runs our
  released images from GHCR, pinned by digest through the packaged images lock,
  with the station directory (the one holding ``pluginlake.toml``) as compose
  project directory: it holds ``.env.production`` and the ``secrets/`` directory
  with one file per password. Projects are not installed in this stack yet.
- Dev (``--dev``): the dev compose of a source checkout, built from source. A
  generated override mounts local project checkouts and passes
  ``$PLUGINLAKE_PROJECTS``, which the dev images install at start, so discovery
  wires their code locations and routers (ADR-009).

``[station] dashboards``, ``lineage`` and ``[monitoring]`` switch the ``ui``,
``lineage`` and ``monitoring`` compose profiles on in both stacks.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pluginlake.deploy.config import CONTAINER_PROJECTS_DIR, StationConfig, StationSettings, load_station_config
from pluginlake.deploy.images import PROD_COMPOSE_FILE, STACK_DIR, ImageLockError, released_image_env
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_DEV_COMPOSE_PARTS = ("deploy", "compose", "docker-compose.dev.yaml")
_MOUNTED_SERVICES = ("dagster", "pluginlake")
_UI_PROFILE = "ui"
_LINEAGE_PROFILE = "lineage"
MONITORING_PROFILE = "monitoring"
_ALL_PROFILES = (_UI_PROFILE, _LINEAGE_PROFILE, MONITORING_PROFILE)
REMOTE_WRITE_SECRET_VAR = "PROMETHEUS_REMOTE_WRITE_PASSWORD"  # noqa: S105 (variable name, not a value)
# Marquez API inside the compose network; the bridge appends /api/v1/lineage.
_MARQUEZ_URL = "http://marquez:5000"
# The service that runs Dagster code (and so emits lineage) per stack.
_DEV_LINEAGE_SERVICE = "dagster"
_PROD_LINEAGE_SERVICE = "dagster-code-server"
PROD_ENV_FILE = ".env.production"
SECRETS_DIR = "secrets"
STACK_DIR_VAR = "PLUGINLAKE_STACK_DIR"
# Secret files of the production stack, per compose profile (None: always needed).
_PROD_SECRETS: dict[str | None, tuple[str, ...]] = {
    None: ("postgres_password", "dagster_pg_password", "ducklake_pg_password"),
    MONITORING_PROFILE: ("postgres_exporter_password",),
    _LINEAGE_PROFILE: ("marquez_db_password",),
}
# May be empty (no remote write); created empty when missing.
_REMOTE_WRITE_SECRET_FILE = "prometheus_remote_write_password"  # noqa: S105 (file name, not a value)


def _find_compose_dir() -> Path | None:
    """Locate the dev ``deploy/compose`` directory of a source checkout by walking up from this file."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent.joinpath(*_DEV_COMPOSE_PARTS)
        if candidate.exists():
            return candidate.parent
    return None


def _station_override(config: StationConfig, lineage_service: str) -> dict[str, dict]:
    """Override entries derived from the station settings, shared by both stacks."""
    services: dict[str, dict] = {}
    if config.station.lineage:
        services[lineage_service] = {
            "environment": {
                "OPENLINEAGE_URL": _MARQUEZ_URL,
                "OPENLINEAGE_NAMESPACE": config.station.lineage_namespace,
            }
        }
    if config.monitoring.enabled:
        services["prometheus"] = {"environment": _prometheus_env(config)}
    return services


def _build_override(config: StationConfig, config_path: Path) -> dict:
    """Build the dev compose override wiring projects into the mounted services."""
    specs = config.projects_env()
    volumes: list[str] = []
    for project in config.local_projects:
        host = (config_path.parent / project.path).resolve()  # ty: ignore[unsupported-operator]
        volumes.append(f"{host}:{CONTAINER_PROJECTS_DIR}/{project.path.name}")  # ty: ignore[missing-union-attribute]

    services: dict[str, dict] = {}
    for service in _MOUNTED_SERVICES:
        entry: dict = {"environment": {"PLUGINLAKE_PROJECTS": specs}}
        if volumes:
            entry["volumes"] = volumes
        services[service] = entry
    for name, entry in _station_override(config, _DEV_LINEAGE_SERVICE).items():
        services.setdefault(name, {"environment": {}})["environment"].update(entry["environment"])
    return {"services": services}


def _build_prod_override(config: StationConfig) -> dict:
    """Build the production compose override (lineage and Prometheus settings)."""
    return {"services": _station_override(config, _PROD_LINEAGE_SERVICE)}


def _prometheus_env(config: StationConfig) -> dict[str, str]:
    """Environment for the Prometheus entrypoint derived from ``[monitoring]``."""
    monitoring = config.monitoring
    env = {
        "PROMETHEUS_STATION_ID": monitoring.station_id,
        "PROMETHEUS_SCRAPE_CADVISOR": str(monitoring.cadvisor).lower(),
    }
    # Unset keeps a URL from .env.monitoring; the override would otherwise blank it.
    if monitoring.remote_write_url:
        env["PROMETHEUS_REMOTE_WRITE_URL"] = monitoring.remote_write_url
    return env


def _compose_profiles(settings: StationSettings, *, monitoring: bool = False) -> list[str]:
    """Return the optional compose profiles enabled in the station settings."""
    profiles: list[str] = []
    if settings.dashboards:
        profiles.append(_UI_PROFILE)
    if settings.lineage:
        profiles.append(_LINEAGE_PROFILE)
    if monitoring:
        profiles.append(MONITORING_PROFILE)
    return profiles


def _compose_command(compose_dir: Path, override_path: Path | None, profiles: list[str] | tuple[str, ...]) -> list[str]:
    """Assemble the base ``docker compose`` command of the dev stack."""
    cmd = ["docker", "compose", "-f", str(compose_dir / _DEV_COMPOSE_PARTS[-1])]
    if override_path is not None:
        cmd += ["-f", str(override_path)]
    for profile in profiles:
        cmd += ["--profile", profile]
    return cmd


def _prod_compose_command(
    station_dir: Path, override_path: Path | None, profiles: list[str] | tuple[str, ...]
) -> list[str]:
    """Assemble the base ``docker compose`` command of the packaged production stack."""
    cmd = ["docker", "compose", "--project-directory", str(station_dir), "--env-file", str(station_dir / PROD_ENV_FILE)]
    cmd += ["-f", str(PROD_COMPOSE_FILE)]
    if override_path is not None:
        cmd += ["-f", str(override_path)]
    for profile in profiles:
        cmd += ["--profile", profile]
    return cmd


def _defines(env_file: Path, name: str) -> bool:
    """Whether the dotenv file ``env_file`` assigns ``name`` (to any value, also empty)."""
    if not env_file.is_file():
        return False
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=", re.MULTILINE)
    return bool(pattern.search(env_file.read_text(encoding="utf-8")))


def _compose_env(compose_dir: Path, *, monitoring: bool) -> dict[str, str] | None:
    """Environment for the dev ``docker compose``; ``None`` keeps the current one.

    The remote-write password is a compose secret, so it must be defined whenever
    Prometheus starts. Without remote write it may be empty: an undefined value is
    passed as empty instead of failing. A value from the shell or the compose
    ``.env`` always wins.

    Returns:
        The environment with an empty password added, or ``None`` to keep the current one.
    """
    if not monitoring or REMOTE_WRITE_SECRET_VAR in os.environ:
        return None
    if _defines(compose_dir / ".env", REMOTE_WRITE_SECRET_VAR):
        return None
    return {**os.environ, REMOTE_WRITE_SECRET_VAR: ""}


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> int:
    logger.info("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, env=env, check=False).returncode  # noqa: S603


def _load_config(config_path: Path) -> StationConfig | None:
    try:
        return load_station_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Invalid station config: {exc}", file=sys.stderr)
        return None


def _write_override(override: dict) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pluginlake-override.json", delete=False, encoding="utf-8"
    ) as handle:
        json.dump(override, handle)
        return Path(handle.name)


def _up_args(config: StationConfig, *, detach: bool) -> list[str]:
    args = ["up"]
    if detach:
        args.append("-d")
    if config.monitoring.enabled and not config.monitoring.cadvisor:
        args += ["--scale", "cadvisor=0"]
    return args


def _prod_env(station_dir: Path) -> dict[str, str] | None:
    """Image and stack variables of the production stack; ``None`` (after a message) when unusable."""
    try:
        images = released_image_env()
    except ImageLockError as exc:
        print(f"Cannot start the production stack: {exc}", file=sys.stderr)
        return None
    if not (station_dir / PROD_ENV_FILE).is_file():
        print(
            f"Missing {PROD_ENV_FILE} in {station_dir}. Copy {STACK_DIR / 'templates' / 'env.production.example'} "
            "and fill it in.",
            file=sys.stderr,
        )
        return None
    return {**images, STACK_DIR_VAR: str(STACK_DIR)}


def _check_secrets(station_dir: Path, profiles: list[str]) -> bool:
    """Check the secret files of the production stack; print what is wrong.

    The directory must not be accessible for other host users, while the files
    must be world-readable: the containers run as other (non-root) users and read
    them through a bind mount, which does not cross the directory permissions.
    The remote-write password file is created empty when monitoring is on and it
    is missing (no remote write).

    Returns:
        Whether the secrets are complete.
    """
    secrets_dir = station_dir / SECRETS_DIR
    if not secrets_dir.is_dir():
        print(f"Missing secrets directory {secrets_dir} (docs/guides/docker.md#secrets).", file=sys.stderr)
        return False
    if secrets_dir.stat().st_mode & 0o077:
        print(f"{secrets_dir} is accessible for other users; run: chmod 700 {secrets_dir}", file=sys.stderr)
        return False
    if MONITORING_PROFILE in profiles:
        remote_write = secrets_dir / _REMOTE_WRITE_SECRET_FILE
        if not remote_write.exists():
            remote_write.touch(mode=0o644)
            logger.info("Created empty %s (no remote write)", remote_write)
    needed = [
        name for profile, names in _PROD_SECRETS.items() if profile is None or profile in profiles for name in names
    ]
    missing = [name for name in needed if not (secrets_dir / name).is_file() or not (secrets_dir / name).stat().st_size]
    if missing:
        print(f"Missing or empty secret files in {secrets_dir}: {', '.join(missing)}.", file=sys.stderr)
        return False
    unreadable = [name for name in needed if not (secrets_dir / name).stat().st_mode & 0o004]
    if unreadable:
        logger.warning(
            "Secret files not readable for the container users (expected mode 0644 inside the 0700 directory): %s",
            ", ".join(unreadable),
        )
    return True


def _run_prod_up(config: StationConfig, config_path: Path, *, detach: bool) -> int:
    if config.projects:
        names = ", ".join(p.name for p in config.projects)
        print(
            f"The production stack cannot install projects yet ({names}). Remove [[projects]] from "
            f"{config_path} or run the dev stack from a checkout with 'pluginlake up --dev'.",
            file=sys.stderr,
        )
        return 1
    station_dir = config_path.resolve().parent
    extra = _prod_env(station_dir)
    if extra is None:
        return 1

    profiles = _compose_profiles(config.station, monitoring=config.monitoring.enabled)
    if not _check_secrets(station_dir, profiles):
        return 1
    logger.info("Enabled compose profiles: %s", ", ".join(profiles) or "(none)")
    override_path = _write_override(_build_prod_override(config))
    cmd = _prod_compose_command(station_dir, override_path, profiles) + _up_args(config, detach=detach)
    try:
        return _run(cmd, cwd=station_dir, env={**os.environ, **extra})
    finally:
        override_path.unlink(missing_ok=True)


def _run_dev_up(config: StationConfig, config_path: Path, *, detach: bool, build: bool) -> int:
    compose_dir = _find_compose_dir()
    if compose_dir is None:
        print(
            "Could not locate deploy/compose/docker-compose.dev.yaml: '--dev' needs a pluginlake source "
            "checkout. Without one, run 'pluginlake up' (production stack).",
            file=sys.stderr,
        )
        return 1

    if not (compose_dir / ".env").exists():
        print(
            f"Warning: no {compose_dir / '.env'} found; copy {compose_dir / '.env.example'} first "
            "(postgres credentials etc.).",
            file=sys.stderr,
        )

    override_path = _write_override(_build_override(config, config_path))
    profiles = _compose_profiles(config.station, monitoring=config.monitoring.enabled)
    print(f"Deploying station with projects: {config.projects_env() or '(none)'}")
    logger.info("Enabled compose profiles: %s", ", ".join(profiles) or "(none)")
    cmd = _compose_command(compose_dir, override_path, profiles)
    args = _up_args(config, detach=detach)
    if build:
        args.insert(1, "--build")
    cmd += args
    env = _compose_env(compose_dir, monitoring=config.monitoring.enabled)
    try:
        return _run(cmd, cwd=compose_dir, env=env)
    finally:
        override_path.unlink(missing_ok=True)


def run_up(config_path: Path, *, detach: bool = False, build: bool = True, dev: bool = False) -> int:
    """Bring up the station stack.

    Args:
        config_path: Path to the ``pluginlake.toml`` station config.
        detach: Run containers in the background.
        build: Rebuild images before starting (dev stack only).
        dev: Run the dev stack of a source checkout instead of the packaged production stack.

    Returns:
        Process exit code.
    """
    config = _load_config(config_path)
    if config is None:
        return 1
    if dev:
        return _run_dev_up(config, config_path, detach=detach, build=build)
    return _run_prod_up(config, config_path, detach=detach)


def run_down(*, volumes: bool = False, dev: bool = False, config_path: Path = Path("pluginlake.toml")) -> int:
    """Stop the station stack.

    All optional profiles are activated, so services stay stoppable after they
    are switched off in ``pluginlake.toml``. Bind-mounted data under ``.data/``
    (dev stack) is kept, also with ``volumes``.

    Args:
        volumes: Also remove named volumes (in production: the databases and data).
        dev: Stop the dev stack of a source checkout instead of the production stack.
        config_path: Station config; its directory is the production compose project directory.

    Returns:
        Process exit code.
    """
    if dev:
        compose_dir = _find_compose_dir()
        if compose_dir is None:
            print("Could not locate deploy/compose/docker-compose.dev.yaml: '--dev' needs a checkout.", file=sys.stderr)
            return 1
        cmd = [*_compose_command(compose_dir, None, _ALL_PROFILES), "down"]
        env = None
        cwd = compose_dir
    else:
        station_dir = config_path.resolve().parent
        extra = _prod_env(station_dir)
        if extra is None:
            return 1
        cmd = [*_prod_compose_command(station_dir, None, _ALL_PROFILES), "down"]
        env = {**os.environ, **extra}
        cwd = station_dir
    if volumes:
        cmd.append("-v")
    return _run(cmd, cwd=cwd, env=env)
