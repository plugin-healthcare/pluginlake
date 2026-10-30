"""Shared plumbing for the commands that drive the station's ``docker compose`` stack."""

import contextlib
import shutil
import subprocess
from pathlib import Path

from pluginlake.deploy.config import load_station_config
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

COMPOSE_FILE_PARTS = ("deploy", "compose", "docker-compose.dev.yaml")


def find_compose_dir() -> Path | None:
    """Locate the bundled ``deploy/compose`` directory by walking up from this file.

    Returns:
        The directory, or ``None`` when it is not found (for example outside a source checkout).
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent.joinpath(*COMPOSE_FILE_PARTS)
        if candidate.exists():
            return candidate.parent
    return None


def _succeeds(cmd: list[str]) -> bool:
    """Return whether a command exits with code 0, discarding its output.

    Args:
        cmd: The command to run.

    Returns:
        ``True`` if the exit code is 0.
    """
    return subprocess.run(cmd, capture_output=True, check=False).returncode == 0  # noqa: S603


def check_docker() -> str | None:
    """Check that Docker, the Compose plugin, and the Docker daemon are available.

    Returns:
        An actionable error message, or ``None`` when everything is available.
    """
    if shutil.which("docker") is None:
        return "Docker is not installed or not on PATH. Install it from https://docs.docker.com/get-docker/."
    if not _succeeds(["docker", "compose", "version"]):
        return "The Docker Compose plugin is missing. See https://docs.docker.com/compose/install/."
    if not _succeeds(["docker", "info"]):
        return "The Docker daemon is not reachable. Start Docker and try again."
    return None


def dashboards_enabled(config_path: Path) -> bool:
    """Return whether the station config enables the dashboards profile.

    Falls back to ``True`` (the superset of services) when the config cannot be read,
    so stop, status, and logs still see every service.

    Args:
        config_path: Path to the ``pluginlake.toml`` station config.

    Returns:
        ``True`` if the dashboards profile should be enabled.
    """
    with contextlib.suppress(FileNotFoundError, ValueError):
        return load_station_config(config_path).station.dashboards
    return True


def compose_command(compose_dir: Path, *, dashboards: bool, override_path: Path | None = None) -> list[str]:
    """Assemble the base ``docker compose`` command shared by all stack commands.

    Args:
        compose_dir: The ``deploy/compose`` directory.
        dashboards: Whether to enable the ``ui`` profile.
        override_path: Optional extra compose file to merge on top of the base file.

    Returns:
        The command as an argument list, without a subcommand.
    """
    cmd = ["docker", "compose", "-f", str(compose_dir / COMPOSE_FILE_PARTS[-1])]
    if override_path is not None:
        cmd += ["-f", str(override_path)]
    if dashboards:
        cmd += ["--profile", "ui"]
    return cmd


def run(cmd: list[str], cwd: Path) -> int:
    """Run a command with inherited output.

    Args:
        cmd: The command to run.
        cwd: The working directory.

    Returns:
        The exit code.
    """
    logger.info("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=False).returncode  # noqa: S603


def capture(cmd: list[str], cwd: Path) -> tuple[int, str]:
    """Run a command and capture its output.

    Args:
        cmd: The command to run.
        cwd: The working directory.

    Returns:
        The exit code and the captured stdout.
    """
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    return result.returncode, result.stdout
