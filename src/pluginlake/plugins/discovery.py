"""Discovery of project plugins via the ``pluginlake.projects`` entry point.

This module stays free of any Dagster import so it can be used by the API
process (for router wiring) without pulling in the orchestration stack. The
Dagster code-location loader lives in :mod:`pluginlake.plugins.dagster`.
"""

from importlib import import_module
from importlib.metadata import entry_points

from fastapi import APIRouter

from pluginlake.plugins.manifest import ProjectManifest, RouterSpec
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

ENTRY_POINT_GROUP = "pluginlake.projects"


def discover_manifests() -> list[ProjectManifest]:
    """Discover all registered project manifests.

    Loads every object registered on the ``pluginlake.projects`` entry-point
    group. An entry point may point at a ``ProjectManifest`` instance or a
    zero-argument callable that returns one.

    Returns:
        The discovered manifests, ordered by project id for determinism.

    Raises:
        TypeError: If a registered object is not a ``ProjectManifest``.
    """
    manifests: list[ProjectManifest] = []
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        obj = ep.load()
        manifest = obj() if callable(obj) else obj
        if not isinstance(manifest, ProjectManifest):
            msg = (
                f"Entry point '{ep.name}' in group '{ENTRY_POINT_GROUP}' must resolve to a "
                f"ProjectManifest, got {type(manifest).__name__}."
            )
            raise TypeError(msg)
        logger.info("Discovered project '%s' (catalog=%s).", manifest.id, manifest.catalog)
        manifests.append(manifest)
    return sorted(manifests, key=lambda m: m.id)


def load_router(spec: RouterSpec) -> APIRouter:
    """Import and return the ``APIRouter`` declared by a router spec.

    Args:
        spec: The router spec from a project manifest.

    Returns:
        The imported ``APIRouter`` instance.

    Raises:
        TypeError: If the referenced attribute is not an ``APIRouter``.
    """
    module = import_module(spec.module)
    router = getattr(module, spec.attribute)
    if not isinstance(router, APIRouter):
        msg = f"'{spec.module}:{spec.attribute}' must be an APIRouter, got {type(router).__name__}."
        raise TypeError(msg)
    return router
