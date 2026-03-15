"""FHIR definitions.

Bundles all FHIR-related assets into a single Definitions object.
Use this as a code location for stations that follow the FHIR standard::

    dagster dev -m pluginlake.definitions.fhir
"""

from dagster import AssetKey, Definitions, define_asset_job

from pluginlake.assets.fhir import (
    FHIR_RESOURCE_TYPES,
    OMOP_TARGET_TABLES,
    fhir_raw_tables,
    fhir_to_omop_tables,
)
from pluginlake.assets.fhir_sensor import fhir_folder_sensor
from pluginlake.core.ducklake.io_manager import ducklake_io_manager

fhir_ingest_job = define_asset_job(
    name="fhir_ingest_job",
    selection=[AssetKey(["fhir_raw", rt]) for rt in FHIR_RESOURCE_TYPES]
    + [AssetKey(["fhir_omop_raw", t]) for t in OMOP_TARGET_TABLES]
    + [AssetKey(["omop", t]) for t in OMOP_TARGET_TABLES],
)

defs = Definitions(
    assets=[fhir_raw_tables, fhir_to_omop_tables],
    jobs=[fhir_ingest_job],
    sensors=[fhir_folder_sensor],
    resources={"io_manager": ducklake_io_manager},
)
