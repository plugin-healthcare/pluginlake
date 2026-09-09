"""Compose Dagster code locations declared by project manifests.

This is the merged-``Definitions`` loader referenced by
``pluginlake.definitions``. It imports Dagster and is therefore kept separate
from :mod:`pluginlake.plugins.discovery`, which must stay orchestration-free.
"""

from importlib import import_module

from dagster import Definitions

from pluginlake.plugins.discovery import discover_manifests
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def load_merged_definitions() -> Definitions:
    """Build a single ``Definitions`` from every project's code locations.

    Discovers all project manifests and merges the ``Definitions`` exposed by
    each declared code location into one code location for the Dagster server.

    Returns:
        The merged ``Definitions``, or an empty ``Definitions`` if no project
        contributes a code location.
    """
    collected: list[Definitions] = []
    for manifest in discover_manifests():
        for spec in manifest.code_locations:
            module = import_module(spec.module)
            collected.append(getattr(module, spec.attribute))
            logger.info("Loaded code location '%s' for project '%s'.", spec.module, manifest.id)
    if not collected:
        return Definitions()
    return Definitions.merge(*collected)
