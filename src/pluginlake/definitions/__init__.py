"""Dagster code location definitions for pluginlake.

This package provides pre-composed Definitions for common data models.
Each submodule bundles the assets for a specific standard:

- ``pluginlake.definitions.omop``  — OMOP CDM assets (planned)
- ``pluginlake.definitions.fhir``  — FHIR assets (planned)

Stations pick the definition module that matches their data model::

    dagster dev -m pluginlake.definitions.omop

Or import individual assets from ``pluginlake.assets`` and compose
a custom ``Definitions`` in their own repo.

When loaded as ``-m pluginlake.definitions`` (the default), this
module exposes a combined ``defs`` that merges all submodule assets.
"""

from dagster import Definitions

from pluginlake.definitions.fhir import defs as fhir_defs
from pluginlake.definitions.omop import defs as omop_defs

defs = Definitions.merge(omop_defs, fhir_defs)
