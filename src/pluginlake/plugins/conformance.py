"""The project conformance suite (``pluginlake verify``).

Because the network is federated and no node can be centrally forced,
standardization is enforced bottom-up: every node re-verifies the plugin
contract on what it receives (ADR-009). This module is that machine-checkable
gate. A package is a valid project only if it passes:

- its manifest validates (guaranteed by :class:`ProjectManifest`);
- the required core version range is satisfied by the running platform;
- its declared code locations, routers, and connectors import and have the
  right types;
- its settings load;
- and, across all installed projects, ids, catalogs, and namespaces are unique.

The suite stays orchestration-free: Dagster is only imported opportunistically
to type-check code locations, never required.
"""

from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

from pluginlake.plugins.base import Connector, ProjectSettings
from pluginlake.plugins.discovery import discover_manifests
from pluginlake.plugins.manifest import ProjectManifest

CORE_PACKAGE = "pluginlake"


class ConformanceError(Exception):
    """Raised when one or more projects fail the conformance suite."""


@dataclass(frozen=True)
class Issue:
    """A single conformance problem, scoped to a project.

    Attributes:
        project: The offending project's id (or ``"<global>"`` for cross-project
            checks that are not tied to one project).
        message: A human-readable description of the problem.
    """

    project: str
    message: str

    def __str__(self) -> str:
        """Render the issue as ``[project] message``."""
        return f"[{self.project}] {self.message}"


@dataclass
class ConformanceReport:
    """The outcome of running the conformance suite.

    Attributes:
        issues: All problems found; empty means every project conforms.
    """

    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return ``True`` if no conformance issues were found."""
        return not self.issues

    def format(self) -> str:
        """Render the report as a human-readable multi-line string."""
        if self.ok:
            return "All projects conform."
        lines = ["Conformance failed:"]
        lines.extend(f"  - {issue}" for issue in self.issues)
        return "\n".join(lines)

    def raise_for_status(self) -> None:
        """Raise :class:`ConformanceError` if any issues were found.

        Raises:
            ConformanceError: If the report is not clean.
        """
        if not self.ok:
            raise ConformanceError(self.format())


def core_version() -> str:
    """Return the installed core (``pluginlake``) version.

    Returns:
        The installed version string, or ``"0"`` if the package metadata is not
        available (for example in some editable/test contexts).
    """
    try:
        return version(CORE_PACKAGE)
    except PackageNotFoundError:
        return "0"


def _check_core_compatibility(manifest: ProjectManifest, installed: str) -> list[Issue]:
    if not manifest.requires_core:
        return []
    try:
        specifier = SpecifierSet(manifest.requires_core)
    except InvalidSpecifier:
        return [Issue(manifest.id, f"requires_core is not a valid PEP 440 specifier: {manifest.requires_core!r}")]
    if Version(installed) not in specifier:
        return [
            Issue(
                manifest.id,
                f"requires core {manifest.requires_core}, but installed core is {installed}.",
            )
        ]
    return []


def _check_imports(manifest: ProjectManifest) -> list[Issue]:
    issues: list[Issue] = []

    for spec in manifest.code_locations:
        try:
            spec.load()
        except (ImportError, AttributeError) as exc:
            issues.append(Issue(manifest.id, f"code location '{spec.module}:{spec.attribute}' failed to load: {exc}"))

    for spec in manifest.routers:
        try:
            router = spec.load()
        except (ImportError, AttributeError) as exc:
            issues.append(Issue(manifest.id, f"router '{spec.module}:{spec.attribute}' failed to load: {exc}"))
            continue
        if not isinstance(router, APIRouter):
            issues.append(
                Issue(
                    manifest.id,
                    f"router '{spec.module}:{spec.attribute}' is not an APIRouter (got {type(router).__name__}).",
                )
            )

    for spec in manifest.connectors:
        try:
            connector = spec.load()
        except (ImportError, AttributeError) as exc:
            issues.append(Issue(manifest.id, f"connector '{spec.module}:{spec.attribute}' failed to load: {exc}"))
            continue
        if not (isinstance(connector, type) and issubclass(connector, Connector)):
            issues.append(
                Issue(manifest.id, f"connector '{spec.module}:{spec.attribute}' must be a Connector subclass.")
            )

    return issues


def _check_settings(manifest: ProjectManifest) -> list[Issue]:
    if manifest.settings is None:
        return []
    try:
        settings_cls = manifest.settings.load()
    except (ImportError, AttributeError) as exc:
        return [
            Issue(
                manifest.id,
                f"settings '{manifest.settings.module}:{manifest.settings.attribute}' failed to load: {exc}",
            )
        ]
    if not (isinstance(settings_cls, type) and issubclass(settings_cls, ProjectSettings)):
        return [
            Issue(
                manifest.id,
                f"settings '{manifest.settings.module}:{manifest.settings.attribute}' must be a ProjectSettings subclass.",
            )
        ]
    try:
        settings_cls()
    except Exception as exc:  # noqa: BLE001 - any settings-load failure is a conformance failure
        return [Issue(manifest.id, f"settings failed to load with defaults: {exc}")]
    return []


def verify_manifest(manifest: ProjectManifest, installed_core: str | None = None) -> list[Issue]:
    """Run all single-project conformance checks for one manifest.

    Args:
        manifest: The project manifest to verify.
        installed_core: Core version to check ``requires_core`` against; defaults
            to the installed core version.

    Returns:
        The issues found; empty means this manifest conforms in isolation.
    """
    installed = installed_core or core_version()
    issues: list[Issue] = []
    issues.extend(_check_core_compatibility(manifest, installed))
    issues.extend(_check_imports(manifest))
    issues.extend(_check_settings(manifest))
    return issues


def _check_uniqueness(manifests: list[ProjectManifest]) -> list[Issue]:
    issues: list[Issue] = []
    for attr, label in (("id", "project id"), ("catalog", "catalog"), ("namespace", "namespace")):
        seen: dict[str, str] = {}
        for manifest in manifests:
            value = getattr(manifest, attr)
            if value in seen:
                issues.append(Issue(manifest.id, f"{label} {value!r} is already used by project {seen[value]!r}."))
            else:
                seen[value] = manifest.id
    return issues


def verify_all(manifests: list[ProjectManifest] | None = None, installed_core: str | None = None) -> ConformanceReport:
    """Verify every project against the plugin contract.

    Args:
        manifests: Manifests to verify; defaults to all discovered manifests.
        installed_core: Core version to check compatibility against; defaults to
            the installed core version.

    Returns:
        A :class:`ConformanceReport` aggregating all issues.
    """
    resolved = manifests if manifests is not None else discover_manifests()
    installed = installed_core or core_version()
    report = ConformanceReport()
    for manifest in resolved:
        report.issues.extend(verify_manifest(manifest, installed))
    report.issues.extend(_check_uniqueness(resolved))
    return report
