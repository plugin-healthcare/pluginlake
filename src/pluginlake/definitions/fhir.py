"""FHIR definitions.

Bundles all FHIR-related assets into a single Definitions object.
Use this as a code location for stations that follow the FHIR standard::

    dagster dev -m pluginlake.definitions.fhir
"""

from dagster import Definitions

from pluginlake.core.ducklake.io_manager import ducklake_io_manager

# Import FHIR assets here once implemented.
# from pluginlake.assets.fhir import fhir_patient, fhir_encounter, ...

defs = Definitions(
    assets=[],
    resources={"io_manager": ducklake_io_manager},
)
