"""OMOP CDM definitions.

Bundles all OMOP-related assets into a single Definitions object.
Use this as a code location for stations that follow the OMOP CDM::

    dagster dev -m pluginlake.definitions.omop
"""

from dagster import AssetKey, Definitions, define_asset_job

from pluginlake.assets.omop import CLINICAL_TABLES, omop_clinical_tables, omop_vocabulary_tables
from pluginlake.core.ducklake.io_manager import ducklake_io_manager

omop_ingest_job = define_asset_job(
    name="omop_ingest_job",
    selection=[AssetKey(["omop", t]) for t in CLINICAL_TABLES],
)

defs = Definitions(
    assets=[omop_clinical_tables, omop_vocabulary_tables],
    jobs=[omop_ingest_job],
    resources={"io_manager": ducklake_io_manager},
)
