"""OMOP CDM data module.

Provides functions for loading, validating, and querying OMOP Common Data Model data.
"""

from pluginlake.omop.config import OMOPSettings, get_omop_settings
from pluginlake.omop.loader import load_omop_dataset, load_omop_table
from pluginlake.omop.provisioning import ensure_omop_vocabularies
from pluginlake.omop.queries import (
    get_cohort,
    get_conditions_for_person,
    get_measurement_values,
    get_observations_for_person,
    get_persons,
    get_visits_for_person,
)
from pluginlake.omop.query_utils import QueryError
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
from pluginlake.omop.validation import ValidationError, validate_omop_table_schema
from pluginlake.omop.vocabulary_validation import filter_invalid_rows, write_audit_table

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
    "QueryError",
    "Specimen",
    "ValidationError",
    "VisitDetail",
    "VisitOccurrence",
    "ensure_omop_vocabularies",
    "filter_invalid_rows",
    "get_cohort",
    "get_conditions_for_person",
    "get_measurement_values",
    "get_observations_for_person",
    "get_omop_schema",
    "get_omop_settings",
    "get_persons",
    "get_visits_for_person",
    "load_omop_dataset",
    "load_omop_table",
    "validate_omop_table_schema",
    "write_audit_table",
]
