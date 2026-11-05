"""``pluginlake up`` / ``pluginlake down`` — config-driven stack deployment.

Reads a ``pluginlake.toml`` station config, generates a compose override that
mounts local project checkouts and passes ``$PLUGINLAKE_PROJECTS`` to the
standardized images, and drives the bundled dev compose stack. The images'
entrypoint installs those projects at start, so discovery wires their code
locations and routers automatically (ADR-009). When ``[monitoring]`` is enabled
the ``monitoring`` compose profile (Prometheus and exporters) is started too.
"""

import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pluginlake.deploy.config import CONTAINER_PROJECTS_DIR, StationConfig, load_station_config
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_DEV_COMPOSE_PARTS = ("deploy", "compose", "docker-compose.dev.yaml")
_MOUNTED_SERVICES = ("dagster", "pluginlake")
MONITORING_PROFILE = "monitoring"
REMOTE_WRITE_SECRET_VAR = "PROMETHEUS_REMOTE_WRITE_PASSWORD"  # noqa: S105 (variable name, not a value)


def _find_compose_dir() -> Path | None:
    """Locate the bundled ``deploy/compose`` directory by walking up from this file."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent.joinpath(*_DEV_COMPOSE_PARTS)
        if candidate.exists():
            return candidate.parent
    return None


def _build_override(config: StationConfig, config_path: Path) -> dict:
    """Build a compose override dict wiring projects into the mounted services."""
    specs = config.projects_env()
    volumes: list[str] = []
    for project in config.local_projects:
        host = (config_path.parent / project.path).resolve()  # type: ignore[operator]
        volumes.append(f"{host}:{CONTAINER_PROJECTS_DIR}/{project.path.name}")  # type: ignore[union-attr]

    services: dict[str, dict] = {}
    for service in _MOUNTED_SERVICES:
        entry: dict = {"environment": {"PLUGINLAKE_PROJECTS": specs}}
        if volumes:
            entry["volumes"] = volumes
        services[service] = entry
    if config.monitoring.enabled:
        services["prometheus"] = {"environment": _prometheus_env(config)}
    return {"services": services}


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


def _compose_command(
    compose_dir: Path, *, override_path: Path | None = None, dashboards: bool, monitoring: bool
) -> list[str]:
    """Assemble the base ``docker compose`` command (files and profiles)."""
    cmd = ["docker", "compose", "-f", str(compose_dir / _DEV_COMPOSE_PARTS[-1])]
    if override_path is not None:
        cmd += ["-f", str(override_path)]
    if dashboards:
        cmd += ["--profile", "ui"]
    if monitoring:
        cmd += ["--profile", MONITORING_PROFILE]
    return cmd


def _defines(env_file: Path, name: str) -> bool:
    """Whether the dotenv file ``env_file`` assigns ``name`` (to any value, also empty)."""
    if not env_file.is_file():
        return False
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=", re.MULTILINE)
    return bool(pattern.search(env_file.read_text(encoding="utf-8")))


def _compose_env(compose_dir: Path, *, monitoring: bool) -> dict[str, str] | None:
    """Environment for ``docker compose up``; ``None`` keeps the current one.

    The remote-write password is a compose secret, so it must be defined whenever
    Prometheus starts. Without remote write it may be empty: an undefined value is
    passed as empty instead of failing. A value from the shell or the compose
    ``.env`` always wins.
    """
    if not monitoring or REMOTE_WRITE_SECRET_VAR in os.environ:
        return None
    if _defines(compose_dir / ".env", REMOTE_WRITE_SECRET_VAR):
        return None
    return {**os.environ, REMOTE_WRITE_SECRET_VAR: ""}


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> int:
    logger.info("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, env=env, check=False).returncode  # noqa: S603


def run_up(config_path: Path, *, detach: bool = False, build: bool = True) -> int:
    """Bring up the station stack with the configured projects.

    Args:
        config_path: Path to the ``pluginlake.toml`` station config.
        detach: Run containers in the background.
        build: Rebuild images before starting.

    Returns:
        Process exit code.
    """
    compose_dir = _find_compose_dir()
    if compose_dir is None:
        print(
            "Could not locate the bundled deploy/compose stack. Run 'pluginlake up' from a "
            "pluginlake source checkout (packaged deploy assets are not yet supported).",
            file=sys.stderr,
        )
        return 1

    try:
        config = load_station_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Invalid station config: {exc}", file=sys.stderr)
        return 1

    if not (compose_dir / ".env").exists():
        print(
            f"Warning: no {compose_dir / '.env'} found; copy {compose_dir / '.env.example'} first "
            "(postgres credentials etc.).",
            file=sys.stderr,
        )

    override = _build_override(config, config_path)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pluginlake-projects.json", delete=False, encoding="utf-8"
    ) as handle:
        json.dump(override, handle)
        override_path = Path(handle.name)

    print(f"Deploying station with projects: {config.projects_env() or '(none)'}")
    monitoring = config.monitoring
    cmd = _compose_command(
        compose_dir,
        override_path=override_path,
        dashboards=config.station.dashboards,
        monitoring=monitoring.enabled,
    )
    cmd.append("up")
    if build:
        cmd.append("--build")
    if detach:
        cmd.append("-d")
    if monitoring.enabled and not monitoring.cadvisor:
        cmd += ["--scale", "cadvisor=0"]
    try:
        return _run(cmd, cwd=compose_dir, env=_compose_env(compose_dir, monitoring=monitoring.enabled))
    finally:
        override_path.unlink(missing_ok=True)


def run_down(config_path: Path, *, volumes: bool = False) -> int:
    """Stop the station stack.

    Args:
        config_path: Path to the ``pluginlake.toml`` station config.
        volumes: Also remove named volumes.

    Returns:
        Process exit code.
    """
    compose_dir = _find_compose_dir()
    if compose_dir is None:
        print("Could not locate the bundled deploy/compose stack.", file=sys.stderr)
        return 1

    dashboards = True
    with contextlib.suppress(FileNotFoundError, ValueError):
        dashboards = load_station_config(config_path).station.dashboards

    # Always include monitoring so its containers stop even if it was switched off since `up`.
    cmd = _compose_command(compose_dir, dashboards=dashboards, monitoring=True)
    cmd.append("down")
    if volumes:
        cmd.append("-v")
    return _run(cmd, cwd=compose_dir)
