"""``pluginlake status`` / ``pluginlake logs`` — inspect the running station stack."""

import json
from pathlib import Path

from pluginlake.cli.console import err, out
from pluginlake.cli.stack import capture, check_docker, compose_command, dashboards_enabled, find_compose_dir, run

_HEALTHY_STATES = ("", "healthy")


def parse_ps_output(text: str) -> list[dict]:
    """Parse ``docker compose ps --format json`` output (a JSON array or one object per line).

    Args:
        text: The raw command output.

    Returns:
        One dict per container.
    """
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _is_ok(container: dict) -> bool:
    """Return whether a container is running and, if it has a healthcheck, healthy.

    Args:
        container: One entry from ``parse_ps_output``.

    Returns:
        ``True`` if the container is running and not unhealthy or still starting.
    """
    return container.get("State") == "running" and container.get("Health", "") in _HEALTHY_STATES


def run_status(config_path: Path) -> int:
    """Show per-service state and health of the station stack.

    Args:
        config_path: Path to the ``pluginlake.toml`` station config.

    Returns:
        ``0`` if every service is running and healthy, ``1`` otherwise.
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
    code, stdout = capture([*cmd, "ps", "-a", "--format", "json"], cwd=compose_dir)
    if code != 0:
        err("Could not read the stack status from docker compose.")
        return 1

    containers = parse_ps_output(stdout)
    if not containers:
        out("No services found. Start the station with 'pluginlake up'.")
        return 1

    for container in sorted(containers, key=lambda c: c.get("Service", "")):
        health = container.get("Health") or "-"
        out(f"{container.get('Service', '?'):<24} {container.get('State', '?'):<12} {health}")
    return 0 if all(_is_ok(c) for c in containers) else 1


def run_logs(config_path: Path, service: str | None = None, *, follow: bool = False) -> int:
    """Show the logs of the station stack.

    Args:
        config_path: Path to the ``pluginlake.toml`` station config.
        service: Only show the logs of this compose service.
        follow: Keep streaming new log lines.

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

    cmd = [*compose_command(compose_dir, dashboards=dashboards_enabled(config_path)), "logs"]
    if follow:
        cmd.append("-f")
    if service is not None:
        cmd.append(service)
    return run(cmd, cwd=compose_dir)
