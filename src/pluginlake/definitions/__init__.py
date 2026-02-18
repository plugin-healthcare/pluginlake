"""Dagster code location definitions for pluginlake.

This package provides pre-composed Definitions for common data models.
Each submodule bundles the assets for a specific standard:

- ``pluginlake.definitions.omop``  — OMOP CDM assets (planned)
- ``pluginlake.definitions.fhir``  — FHIR assets (planned)

Stations pick the definition module that matches their data model::

    dagster dev -m pluginlake.definitions.omop

Or import individual assets from ``pluginlake.assets`` and compose
a custom ``Definitions`` in their own repo.
"""
