"""OMOP CDM definitions.

Bundles all OMOP-related assets into a single Definitions object.
Use this as a code location for stations that follow the OMOP CDM::

    dagster dev -m pluginlake.definitions.omop
"""

from dagster import Definitions

# Import OMOP assets here once implemented.
# from pluginlake.assets.omop import omop_condition, omop_observation, ...

defs = Definitions(assets=[])
