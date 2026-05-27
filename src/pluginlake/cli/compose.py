"""Docker Compose wrappers for managing pluginlake instances."""

import subprocess
import sys
from pathlib import Path

from pluginlake.cli.paths import instance_config_dir, list_instances
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

# Compose file path relative to the package source
_COMPOSE_FILE = Path(__file__).resolve().parents[3] / "deploy" / "compose" / "docker-compose.yaml"


def _resolve_compose_file() -> Path:
    """Find the docker-compose.yaml for production deployments."""
    if _COMPOSE_FILE.exists():
        return _COMPOSE_FILE
    # Fallback: try installed package location
    msg = f"Compose file not found at {_COMPOSE_FILE}. Are you in the pluginlake repository?"
    raise FileNotFoundError(msg)


def _compose_cmd(instance_id: str, args: list[str], profile: str | None = None) -> list[str]:
    """Build the docker compose command with env file and project name."""
    compose_file = _resolve_compose_file()
    config_dir = instance_config_dir(instance_id)
    env_file = config_dir / ".env"

    if not env_file.exists():
        msg = f"Instance '{instance_id}' not initialized. Run: pluginlake init"
        raise FileNotFoundError(msg)

    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "--env-file",
        str(env_file),
        "-p",
        f"pluginlake-{instance_id}",
    ]

    if profile:
        cmd.extend(["--profile", profile])

    return [*cmd, *args]


def run_up(instance_id: str, profile: str | None = None, *, build: bool = True) -> int:
    """Start services for an instance.

    Args:
        instance_id: The datastation instance ID.
        profile: Optional compose profile (e.g. 'ui').
        build: Whether to build images.

    Returns:
        Subprocess exit code.
    """
    args = ["up", "-d"]
    if build:
        args.append("--build")

    cmd = _compose_cmd(instance_id, args, profile=profile)
    logger.info("Starting instance: %s", instance_id)
    return subprocess.call(cmd)  # noqa: S603


def run_down(instance_id: str, *, volumes: bool = False) -> int:
    """Stop services for an instance.

    Args:
        instance_id: The datastation instance ID.
        volumes: Whether to remove volumes.

    Returns:
        Subprocess exit code.
    """
    args = ["down"]
    if volumes:
        args.append("-v")

    cmd = _compose_cmd(instance_id, args)
    logger.info("Stopping instance: %s", instance_id)
    return subprocess.call(cmd)  # noqa: S603


def run_status(instance_id: str) -> int:
    """Show container status for an instance.

    Args:
        instance_id: The datastation instance ID.

    Returns:
        Subprocess exit code.
    """
    cmd = _compose_cmd(instance_id, ["ps", "--format", "table"])
    return subprocess.call(cmd)  # noqa: S603


def run_list() -> None:
    """List all initialized pluginlake instances."""
    instances = list_instances()
    if not instances:
        print("No instances found. Run: pluginlake init")
        sys.exit(0)

    print(f"{'Instance ID':<30} {'Config'}")
    print("-" * 60)
    for inst in instances:
        config = instance_config_dir(inst)
        print(f"{inst:<30} {config}")
