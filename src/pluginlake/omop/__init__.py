"""OMOP CDM data module.

Provides functions for loading, validating, and querying OMOP Common Data Model data.
"""

from pluginlake.omop.config import OMOPSettings, get_omop_settings
from pluginlake.omop.loader import load_omop_dataset, load_omop_table
from pluginlake.omop.schemas import (
    OMOP_SCHEMAS,
    ConditionOccurrence,
    Death,
    DeviceExposure,
    DrugExposure,
    FactRelationship,
    Measurement,
    Note,
    NoteNlp,
    Observation,
    ObservationPeriod,
    Person,
    ProcedureOccurrence,
    Specimen,
    VisitDetail,
    VisitOccurrence,
    get_omop_schema,
)
from pluginlake.omop.storage import (
    get_duckdb_connection,
    load_parquet_as_polars,
    query_duckdb,
    register_omop_tables,
    save_omop_table,
)
from pluginlake.omop.validation import ValidationError, validate_omop_table_schema

__all__ = [
    "OMOP_SCHEMAS",
    "ConditionOccurrence",
    "Death",
    "DeviceExposure",
    "DrugExposure",
    "FactRelationship",
    "Measurement",
    "Note",
    "NoteNlp",
    "OMOPSettings",
    "Observation",
    "ObservationPeriod",
    "Person",
    "ProcedureOccurrence",
    "Specimen",
    "ValidationError",
    "VisitDetail",
    "VisitOccurrence",
    "get_duckdb_connection",
    "get_omop_schema",
    "get_omop_settings",
    "load_omop_dataset",
    "load_omop_table",
    "load_parquet_as_polars",
    "query_duckdb",
    "register_omop_tables",
    "save_omop_table",
    "validate_omop_table_schema",
]
