"""Dagster code location for pluginlake.

Loaded by the Dagster code server as ``-m pluginlake.definitions``. The
combined ``defs`` is composed from the code locations declared by every
discovered project manifest (ADR-009), rather than importing project modules
directly. Target a single project's code location directly if preferred::

    dagster dev -m pluginlake.definitions.omop
"""

from pluginlake.plugins.dagster import load_merged_definitions

defs = load_merged_definitions()
