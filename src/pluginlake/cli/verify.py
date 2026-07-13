"""``pluginlake verify`` — run the conformance suite."""

import sys

from pluginlake.plugins.conformance import verify_all
from pluginlake.plugins.discovery import discover_manifests


def run_verify(project: str | None = None) -> int:
    """Verify installed project packages against the plugin contract.

    Args:
        project: If given, only verify the project with this id.

    Returns:
        ``0`` if all verified projects conform, ``1`` otherwise.
    """
    manifests = discover_manifests()
    if project is not None:
        manifests = [m for m in manifests if m.id == project]
        if not manifests:
            print(f"No installed project with id '{project}'.", file=sys.stderr)
            return 1

    if not manifests:
        print("No projects installed. Nothing to verify.")
        return 0

    report = verify_all(manifests)
    stream = sys.stdout if report.ok else sys.stderr
    print(report.format(), file=stream)
    return 0 if report.ok else 1
