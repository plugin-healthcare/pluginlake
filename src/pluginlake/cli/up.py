"""``pluginlake up`` / ``pluginlake down`` — config-driven stack deployment.

Reads a ``pluginlake.toml`` station config, generates a compose override that
mounts local project checkouts and passes ``$PLUGINLAKE_PROJECTS`` to the
standardized images, and drives the bundled dev compose stack. The images'
entrypoint installs those projects at start, so discovery wires their code
locations and routers automatically (ADR-009).
"""

import contextlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from pluginlake.deploy.config import CONTAINER_PROJECTS_DIR, StationConfig, load_station_config
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_DEV_COMPOSE_PARTS = ("deploy", "compose", "docker-compose.dev.yaml")
_MOUNTED_SERVICES = ("dagster", "pluginlake")


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
    return {"services": services}


def _compose_command(compose_dir: Path, override_path: Path, *, dashboards: bool) -> list[str]:
    """Assemble the base ``docker compose`` command shared by up and down."""
    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_dir / _DEV_COMPOSE_PARTS[-1]),
        "-f",
        str(override_path),
    ]
    if dashboards:
        cmd += ["--profile", "ui"]
    return cmd


def _run(cmd: list[str], cwd: Path) -> int:
    logger.info("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=False).returncode  # noqa: S603


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
    cmd = _compose_command(compose_dir, override_path, dashboards=config.station.dashboards)
    cmd.append("up")
    if build:
        cmd.append("--build")
    if detach:
        cmd.append("-d")
    return _run(cmd, cwd=compose_dir)


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

    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_dir / _DEV_COMPOSE_PARTS[-1]),
    ]
    if dashboards:
        cmd += ["--profile", "ui"]
    cmd.append("down")
    if volumes:
        cmd.append("-v")
    return _run(cmd, cwd=compose_dir)
