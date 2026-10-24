"""``pluginlake verify`` — run the conformance suite."""

from pluginlake.cli.console import err, out
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
            err(f"No installed project with id '{project}'.")
            return 1

    if not manifests:
        out("No projects installed. Nothing to verify.")
        return 0

    report = verify_all(manifests)
    (out if report.ok else err)(report.format())
    return 0 if report.ok else 1
