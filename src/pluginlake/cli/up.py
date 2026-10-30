"""``pluginlake up`` / ``pluginlake down`` — config-driven stack deployment.

Reads a ``pluginlake.toml`` station config, generates a compose override that
mounts local project checkouts and passes ``$PLUGINLAKE_PROJECTS`` to the
standardized images, and drives the bundled dev compose stack. The images'
entrypoint installs those projects at start, so discovery wires their code
locations and routers automatically (ADR-009).
"""

import json
import tempfile
from pathlib import Path

from pluginlake.cli.console import err, out
from pluginlake.cli.stack import check_docker, compose_command, dashboards_enabled, find_compose_dir, run
from pluginlake.deploy.config import CONTAINER_PROJECTS_DIR, StationConfig, load_station_config

_MOUNTED_SERVICES = ("dagster", "pluginlake")


def _build_override(config: StationConfig, config_path: Path) -> dict:
    """Build a compose override dict wiring projects into the mounted services.

    Args:
        config: The station config.
        config_path: Path to the station config, used to resolve relative project paths.

    Returns:
        The compose override as a dict.
    """
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
    return {"services": services}


def run_up(config_path: Path, *, attach: bool = False, build: bool = True) -> int:
    """Bring up the station stack with the configured projects and wait until it is healthy.

    Runs ``docker compose up -d --wait``, so the command returns once the services are
    healthy. Running it again on a running stack leaves it unchanged.

    Args:
        config_path: Path to the ``pluginlake.toml`` station config.
        attach: Follow the logs after the stack is up.
        build: Rebuild images before starting.

    Returns:
        Process exit code.
    """
    problem = check_docker()
    if problem is not None:
        err(problem)
        return 1

    compose_dir = find_compose_dir()
    if compose_dir is None:
        err(
            "Could not locate the bundled deploy/compose stack. Run 'pluginlake up' from a "
            "pluginlake source checkout (packaged deploy assets are not yet supported)."
        )
        return 1

    try:
        config = load_station_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        err(f"Invalid station config: {exc}")
        return 1

    if not (compose_dir / ".env").exists():
        err(
            f"Warning: no {compose_dir / '.env'} found; copy {compose_dir / '.env.example'} first "
            "(postgres credentials etc.)."
        )

    with tempfile.TemporaryDirectory() as tmp:
        override_path = Path(tmp) / "pluginlake-projects.json"
        override_path.write_text(json.dumps(_build_override(config, config_path)), encoding="utf-8")

        out(f"Deploying station with projects: {config.projects_env() or '(none)'}")
        cmd = compose_command(compose_dir, dashboards=config.station.dashboards, override_path=override_path)
        cmd += ["up", "-d", "--wait"]
        if build:
            cmd.append("--build")
        code = run(cmd, cwd=compose_dir)

    if code != 0:
        err("The station did not become healthy. Run 'pluginlake status' and 'pluginlake logs' to see why.")
        return code

    out("Station is up. Run 'pluginlake status' to check it.")
    if attach:
        logs_cmd = compose_command(compose_dir, dashboards=config.station.dashboards)
        return run([*logs_cmd, "logs", "-f"], cwd=compose_dir)
    return 0


def run_down(config_path: Path) -> int:
    """Stop the station stack. Volumes and data are never removed.

    Args:
        config_path: Path to the ``pluginlake.toml`` station config.

    Returns:
        Process exit code.
    """
    problem = check_docker()
    if problem is not None:
        err(problem)
        return 1

    compose_dir = find_compose_dir()
    if compose_dir is None:
        err("Could not locate the bundled deploy/compose stack.")
        return 1

    cmd = compose_command(compose_dir, dashboards=dashboards_enabled(config_path))
    return run([*cmd, "down"], cwd=compose_dir)
