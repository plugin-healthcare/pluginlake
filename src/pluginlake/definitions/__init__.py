"""Dagster code location for pluginlake.

Loaded by the Dagster code server as ``-m pluginlake.definitions``. The
combined ``defs`` is composed from the code locations declared by every
discovered project manifest (ADR-009), rather than importing project modules
directly. Core adds the OpenLineage sensor when a lineage backend is
configured (ADR-007). Target a single project's code location directly if preferred::

    dagster dev -m <project_package>.definitions.<code_location>
"""

from dagster import Definitions

from pluginlake.definitions.lineage import lineage_definitions
from pluginlake.plugins.dagster import load_merged_definitions

defs = Definitions.merge(load_merged_definitions(), lineage_definitions())
