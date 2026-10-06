"""Project plugin contract and discovery.

A project package registers itself with core through a single
``ProjectManifest`` exposed on the ``pluginlake.projects`` entry-point group.
Core discovers manifests and wires each project's Dagster code locations and
API routers uniformly. See ADR-009 for the rationale and the target model.
"""
