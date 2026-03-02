"""Dagster code location definitions for pluginlake.

This package provides pre-composed Definitions for common data models.
Each submodule bundles the assets for a specific standard:

- ``pluginlake.definitions.omop``  — OMOP CDM assets
- ``pluginlake.definitions.fhir``  — FHIR assets (planned)

Use this module as the code location to load all definitions::

    dagster dev -m pluginlake.definitions

Or target a specific submodule directly::

    dagster dev -m pluginlake.definitions.omop

Or import individual assets from ``pluginlake.assets`` and compose
a custom ``Definitions`` in their own repo.
"""

from dagster import Definitions

from pluginlake.definitions import fhir as _fhir
from pluginlake.definitions import omop as _omop

defs = Definitions.merge(_omop.defs, _fhir.defs)
