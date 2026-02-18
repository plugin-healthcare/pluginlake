"""OMOP CDM table schemas.

Pydantic models for OMOP CDM v5.4 tables.
Used for validation and type checking.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class Person(BaseModel):
    """OMOP Person table schema."""

    person_id: int = Field(description="Unique person identifier")
    gender_concept_id: int = Field(description="Gender concept from vocabulary")
    year_of_birth: int = Field(description="Year of birth")
    month_of_birth: int | None = Field(default=None, description="Month of birth")
    day_of_birth: int | None = Field(default=None, description="Day of birth")
    birth_datetime: datetime | None = Field(default=None, description="Birth datetime")
    race_concept_id: int = Field(description="Race concept from vocabulary")
    ethnicity_concept_id: int = Field(description="Ethnicity concept from vocabulary")
    location_id: int | None = Field(default=None, description="Location foreign key")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    care_site_id: int | None = Field(default=None, description="Care site foreign key")
    person_source_value: str | None = Field(default=None, description="Source person ID")
    gender_source_value: str | None = Field(default=None, description="Source gender value")
    gender_source_concept_id: int | None = Field(default=None, description="Source gender concept")
    race_source_value: str | None = Field(default=None, description="Source race value")
    race_source_concept_id: int | None = Field(default=None, description="Source race concept")
    ethnicity_source_value: str | None = Field(default=None, description="Source ethnicity value")
    ethnicity_source_concept_id: int | None = Field(default=None, description="Source ethnicity concept")


class ObservationPeriod(BaseModel):
    """OMOP Observation Period table schema."""

    observation_period_id: int = Field(description="Unique observation period identifier")
    person_id: int = Field(description="Person foreign key")
    observation_period_start_date: date = Field(description="Start date of observation period")
    observation_period_end_date: date = Field(description="End date of observation period")
    period_type_concept_id: int = Field(description="Period type concept")


class VisitOccurrence(BaseModel):
    """OMOP Visit Occurrence table schema."""

    visit_occurrence_id: int = Field(description="Unique visit occurrence identifier")
    person_id: int = Field(description="Person foreign key")
    visit_concept_id: int = Field(description="Visit concept from vocabulary")
    visit_start_date: date = Field(description="Visit start date")
    visit_start_datetime: datetime | None = Field(default=None, description="Visit start datetime")
    visit_end_date: date = Field(description="Visit end date")
    visit_end_datetime: datetime | None = Field(default=None, description="Visit end datetime")
    visit_type_concept_id: int = Field(description="Visit type concept")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    care_site_id: int | None = Field(default=None, description="Care site foreign key")
    visit_source_value: str | None = Field(default=None, description="Source visit value")
    visit_source_concept_id: int | None = Field(default=None, description="Source visit concept")
    admitted_from_concept_id: int | None = Field(default=None, description="Admitted from concept")
    admitted_from_source_value: str | None = Field(default=None, description="Admitted from source value")
    discharged_to_concept_id: int | None = Field(default=None, description="Discharged to concept")
    discharged_to_source_value: str | None = Field(default=None, description="Discharged to source value")
    preceding_visit_occurrence_id: int | None = Field(default=None, description="Preceding visit foreign key")


class VisitDetail(BaseModel):
    """OMOP Visit Detail table schema."""

    visit_detail_id: int = Field(description="Unique visit detail identifier")
    person_id: int = Field(description="Person foreign key")
    visit_detail_concept_id: int = Field(description="Visit detail concept from vocabulary")
    visit_detail_start_date: date = Field(description="Visit detail start date")
    visit_detail_start_datetime: datetime | None = Field(default=None, description="Visit detail start datetime")
    visit_detail_end_date: date = Field(description="Visit detail end date")
    visit_detail_end_datetime: datetime | None = Field(default=None, description="Visit detail end datetime")
    visit_detail_type_concept_id: int = Field(description="Visit detail type concept")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    care_site_id: int | None = Field(default=None, description="Care site foreign key")
    visit_detail_source_value: str | None = Field(default=None, description="Source visit detail value")
    visit_detail_source_concept_id: int | None = Field(default=None, description="Source visit detail concept")
    admitted_from_concept_id: int | None = Field(default=None, description="Admitted from concept")
    admitted_from_source_value: str | None = Field(default=None, description="Admitted from source value")
    discharged_to_source_value: str | None = Field(default=None, description="Discharged to source value")
    discharged_to_concept_id: int | None = Field(default=None, description="Discharged to concept")
    preceding_visit_detail_id: int | None = Field(default=None, description="Preceding visit detail foreign key")
    parent_visit_detail_id: int | None = Field(default=None, description="Parent visit detail foreign key")
    visit_occurrence_id: int = Field(description="Visit occurrence foreign key")


class ConditionOccurrence(BaseModel):
    """OMOP Condition Occurrence table schema."""

    condition_occurrence_id: int = Field(description="Unique condition occurrence identifier")
    person_id: int = Field(description="Person foreign key")
    condition_concept_id: int = Field(description="Condition concept from vocabulary")
    condition_start_date: date = Field(description="Condition start date")
    condition_start_datetime: datetime | None = Field(default=None, description="Condition start datetime")
    condition_end_date: date | None = Field(default=None, description="Condition end date")
    condition_end_datetime: datetime | None = Field(default=None, description="Condition end datetime")
    condition_type_concept_id: int = Field(description="Condition type concept")
    condition_status_concept_id: int | None = Field(default=None, description="Condition status concept")
    stop_reason: str | None = Field(default=None, description="Stop reason")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    visit_occurrence_id: int | None = Field(default=None, description="Visit occurrence foreign key")
    visit_detail_id: int | None = Field(default=None, description="Visit detail foreign key")
    condition_source_value: str | None = Field(default=None, description="Source condition value")
    condition_source_concept_id: int | None = Field(default=None, description="Source condition concept")
    condition_status_source_value: str | None = Field(default=None, description="Source status value")


class DrugExposure(BaseModel):
    """OMOP Drug Exposure table schema."""

    drug_exposure_id: int = Field(description="Unique drug exposure identifier")
    person_id: int = Field(description="Person foreign key")
    drug_concept_id: int = Field(description="Drug concept from vocabulary")
    drug_exposure_start_date: date = Field(description="Drug exposure start date")
    drug_exposure_start_datetime: datetime | None = Field(default=None, description="Drug exposure start datetime")
    drug_exposure_end_date: date = Field(description="Drug exposure end date")
    drug_exposure_end_datetime: datetime | None = Field(default=None, description="Drug exposure end datetime")
    verbatim_end_date: date | None = Field(default=None, description="Verbatim end date")
    drug_type_concept_id: int = Field(description="Drug type concept")
    stop_reason: str | None = Field(default=None, description="Stop reason")
    refills: int | None = Field(default=None, description="Number of refills")
    quantity: float | None = Field(default=None, description="Quantity")
    days_supply: int | None = Field(default=None, description="Days supply")
    sig: str | None = Field(default=None, description="Sig")
    route_concept_id: int | None = Field(default=None, description="Route concept")
    lot_number: str | None = Field(default=None, description="Lot number")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    visit_occurrence_id: int | None = Field(default=None, description="Visit occurrence foreign key")
    visit_detail_id: int | None = Field(default=None, description="Visit detail foreign key")
    drug_source_value: str | None = Field(default=None, description="Source drug value")
    drug_source_concept_id: int | None = Field(default=None, description="Source drug concept")
    route_source_value: str | None = Field(default=None, description="Route source value")
    dose_unit_source_value: str | None = Field(default=None, description="Dose unit source value")


class ProcedureOccurrence(BaseModel):
    """OMOP Procedure Occurrence table schema."""

    procedure_occurrence_id: int = Field(description="Unique procedure occurrence identifier")
    person_id: int = Field(description="Person foreign key")
    procedure_concept_id: int = Field(description="Procedure concept from vocabulary")
    procedure_date: date = Field(description="Procedure date")
    procedure_datetime: datetime | None = Field(default=None, description="Procedure datetime")
    procedure_end_date: date | None = Field(default=None, description="Procedure end date")
    procedure_end_datetime: datetime | None = Field(default=None, description="Procedure end datetime")
    procedure_type_concept_id: int = Field(description="Procedure type concept")
    modifier_concept_id: int | None = Field(default=None, description="Modifier concept")
    quantity: int | None = Field(default=None, description="Quantity")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    visit_occurrence_id: int | None = Field(default=None, description="Visit occurrence foreign key")
    visit_detail_id: int | None = Field(default=None, description="Visit detail foreign key")
    procedure_source_value: str | None = Field(default=None, description="Source procedure value")
    procedure_source_concept_id: int | None = Field(default=None, description="Source procedure concept")
    modifier_source_value: str | None = Field(default=None, description="Modifier source value")


class DeviceExposure(BaseModel):
    """OMOP Device Exposure table schema."""

    device_exposure_id: int = Field(description="Unique device exposure identifier")
    person_id: int = Field(description="Person foreign key")
    device_concept_id: int = Field(description="Device concept from vocabulary")
    device_exposure_start_date: date = Field(description="Device exposure start date")
    device_exposure_start_datetime: datetime | None = Field(default=None, description="Device exposure start datetime")
    device_exposure_end_date: date | None = Field(default=None, description="Device exposure end date")
    device_exposure_end_datetime: datetime | None = Field(default=None, description="Device exposure end datetime")
    device_type_concept_id: int = Field(description="Device type concept")
    unique_device_id: str | None = Field(default=None, description="Unique device ID")
    production_id: str | None = Field(default=None, description="Production ID")
    quantity: int | None = Field(default=None, description="Quantity")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    visit_occurrence_id: int | None = Field(default=None, description="Visit occurrence foreign key")
    visit_detail_id: int | None = Field(default=None, description="Visit detail foreign key")
    device_source_value: str | None = Field(default=None, description="Source device value")
    device_source_concept_id: int | None = Field(default=None, description="Source device concept")
    unit_concept_id: int | None = Field(default=None, description="Unit concept")
    unit_source_value: str | None = Field(default=None, description="Unit source value")
    unit_source_concept_id: int | None = Field(default=None, description="Unit source concept")


class Measurement(BaseModel):
    """OMOP Measurement table schema."""

    measurement_id: int = Field(description="Unique measurement identifier")
    person_id: int = Field(description="Person foreign key")
    measurement_concept_id: int = Field(description="Measurement concept from vocabulary")
    measurement_date: date = Field(description="Measurement date")
    measurement_datetime: datetime | None = Field(default=None, description="Measurement datetime")
    measurement_time: str | None = Field(default=None, description="Measurement time")
    measurement_type_concept_id: int = Field(description="Measurement type concept")
    operator_concept_id: int | None = Field(default=None, description="Operator concept")
    value_as_number: float | None = Field(default=None, description="Value as number")
    value_as_concept_id: int | None = Field(default=None, description="Value as concept")
    unit_concept_id: int | None = Field(default=None, description="Unit concept")
    range_low: float | None = Field(default=None, description="Range low")
    range_high: float | None = Field(default=None, description="Range high")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    visit_occurrence_id: int | None = Field(default=None, description="Visit occurrence foreign key")
    visit_detail_id: int | None = Field(default=None, description="Visit detail foreign key")
    measurement_source_value: str | None = Field(default=None, description="Source measurement value")
    measurement_source_concept_id: int | None = Field(default=None, description="Source measurement concept")
    unit_source_value: str | None = Field(default=None, description="Unit source value")
    unit_source_concept_id: int | None = Field(default=None, description="Unit source concept")
    value_source_value: str | None = Field(default=None, description="Value source value")
    measurement_event_id: int | None = Field(default=None, description="Measurement event ID")
    meas_event_field_concept_id: int | None = Field(default=None, description="Measurement event field concept")


class Observation(BaseModel):
    """OMOP Observation table schema."""

    observation_id: int = Field(description="Unique observation identifier")
    person_id: int = Field(description="Person foreign key")
    observation_concept_id: int = Field(description="Observation concept from vocabulary")
    observation_date: date = Field(description="Observation date")
    observation_datetime: datetime | None = Field(default=None, description="Observation datetime")
    observation_type_concept_id: int = Field(description="Observation type concept")
    value_as_number: float | None = Field(default=None, description="Value as number")
    value_as_string: str | None = Field(default=None, description="Value as string")
    value_as_concept_id: int | None = Field(default=None, description="Value as concept")
    qualifier_concept_id: int | None = Field(default=None, description="Qualifier concept")
    unit_concept_id: int | None = Field(default=None, description="Unit concept")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    visit_occurrence_id: int | None = Field(default=None, description="Visit occurrence foreign key")
    visit_detail_id: int | None = Field(default=None, description="Visit detail foreign key")
    observation_source_value: str | None = Field(default=None, description="Source observation value")
    observation_source_concept_id: int | None = Field(default=None, description="Source observation concept")
    unit_source_value: str | None = Field(default=None, description="Unit source value")
    qualifier_source_value: str | None = Field(default=None, description="Qualifier source value")
    value_source_value: str | None = Field(default=None, description="Value source value")
    observation_event_id: int | None = Field(default=None, description="Observation event ID")
    obs_event_field_concept_id: int | None = Field(default=None, description="Observation event field concept")


class Death(BaseModel):
    """OMOP Death table schema."""

    person_id: int = Field(description="Person foreign key")
    death_date: date = Field(description="Death date")
    death_datetime: datetime | None = Field(default=None, description="Death datetime")
    death_type_concept_id: int = Field(description="Death type concept")
    cause_concept_id: int | None = Field(default=None, description="Cause concept")
    cause_source_value: str | None = Field(default=None, description="Cause source value")
    cause_source_concept_id: int | None = Field(default=None, description="Cause source concept")


class Note(BaseModel):
    """OMOP Note table schema."""

    note_id: int = Field(description="Unique note identifier")
    person_id: int = Field(description="Person foreign key")
    note_date: date = Field(description="Note date")
    note_datetime: datetime | None = Field(default=None, description="Note datetime")
    note_type_concept_id: int = Field(description="Note type concept")
    note_class_concept_id: int = Field(description="Note class concept")
    note_title: str | None = Field(default=None, description="Note title")
    note_text: str = Field(description="Note text")
    encoding_concept_id: int = Field(description="Encoding concept")
    language_concept_id: int = Field(description="Language concept")
    provider_id: int | None = Field(default=None, description="Provider foreign key")
    visit_occurrence_id: int | None = Field(default=None, description="Visit occurrence foreign key")
    visit_detail_id: int | None = Field(default=None, description="Visit detail foreign key")
    note_source_value: str | None = Field(default=None, description="Note source value")
    note_event_id: int | None = Field(default=None, description="Note event ID")
    note_event_field_concept_id: int | None = Field(default=None, description="Note event field concept")


class NoteNlp(BaseModel):
    """OMOP Note NLP table schema."""

    note_nlp_id: int = Field(description="Unique note NLP identifier")
    note_id: int = Field(description="Note foreign key")
    section_concept_id: int | None = Field(default=None, description="Section concept")
    snippet: str | None = Field(default=None, description="Snippet")
    offset: str | None = Field(default=None, description="Offset")
    lexical_variant: str = Field(description="Lexical variant")
    note_nlp_concept_id: int | None = Field(default=None, description="Note NLP concept")
    note_nlp_source_concept_id: int | None = Field(default=None, description="Note NLP source concept")
    nlp_system: str | None = Field(default=None, description="NLP system")
    nlp_date: date = Field(description="NLP date")
    nlp_datetime: datetime | None = Field(default=None, description="NLP datetime")
    term_exists: str | None = Field(default=None, description="Term exists")
    term_temporal: str | None = Field(default=None, description="Term temporal")
    term_modifiers: str | None = Field(default=None, description="Term modifiers")


class Specimen(BaseModel):
    """OMOP Specimen table schema."""

    specimen_id: int = Field(description="Unique specimen identifier")
    person_id: int = Field(description="Person foreign key")
    specimen_concept_id: int = Field(description="Specimen concept from vocabulary")
    specimen_type_concept_id: int = Field(description="Specimen type concept")
    specimen_date: date = Field(description="Specimen date")
    specimen_datetime: datetime | None = Field(default=None, description="Specimen datetime")
    quantity: float | None = Field(default=None, description="Quantity")
    unit_concept_id: int | None = Field(default=None, description="Unit concept")
    anatomic_site_concept_id: int | None = Field(default=None, description="Anatomic site concept")
    disease_status_concept_id: int | None = Field(default=None, description="Disease status concept")
    specimen_source_id: str | None = Field(default=None, description="Specimen source ID")
    specimen_source_value: str | None = Field(default=None, description="Specimen source value")
    unit_source_value: str | None = Field(default=None, description="Unit source value")
    anatomic_site_source_value: str | None = Field(default=None, description="Anatomic site source value")
    disease_status_source_value: str | None = Field(default=None, description="Disease status source value")


class ConditionEra(BaseModel):
    """OMOP Condition Era table schema."""

    condition_era_id: int = Field(description="Unique condition era identifier")
    person_id: int = Field(description="Person foreign key")
    condition_concept_id: int = Field(description="Condition concept from vocabulary")
    condition_era_start_date: date = Field(description="Start date of condition era")
    condition_era_end_date: date = Field(description="End date of condition era")
    condition_occurrence_count: int | None = Field(default=None, description="Number of condition occurrences")


class DrugEra(BaseModel):
    """OMOP Drug Era table schema."""

    drug_era_id: int = Field(description="Unique drug era identifier")
    person_id: int = Field(description="Person foreign key")
    drug_concept_id: int = Field(description="Drug concept from vocabulary")
    drug_era_start_date: date = Field(description="Start date of drug era")
    drug_era_end_date: date = Field(description="End date of drug era")
    drug_exposure_count: int | None = Field(default=None, description="Number of drug exposures")
    gap_days: int | None = Field(default=None, description="Gap days")


class FactRelationship(BaseModel):
    """OMOP Fact Relationship table schema."""

    domain_concept_id_1: int = Field(description="Domain concept 1")
    fact_id_1: int = Field(description="Fact ID 1")
    domain_concept_id_2: int = Field(description="Domain concept 2")
    fact_id_2: int = Field(description="Fact ID 2")
    relationship_concept_id: int = Field(description="Relationship concept")


OMOP_SCHEMAS: dict[str, type[BaseModel]] = {
    "person": Person,
    "observation_period": ObservationPeriod,
    "visit_occurrence": VisitOccurrence,
    "visit_detail": VisitDetail,
    "condition_occurrence": ConditionOccurrence,
    "drug_exposure": DrugExposure,
    "procedure_occurrence": ProcedureOccurrence,
    "device_exposure": DeviceExposure,
    "measurement": Measurement,
    "observation": Observation,
    "death": Death,
    "note": Note,
    "note_nlp": NoteNlp,
    "specimen": Specimen,
    "condition_era": ConditionEra,
    "drug_era": DrugEra,
    "fact_relationship": FactRelationship,
}


def get_omop_schema(table_name: str) -> type[BaseModel] | None:
    """Get Pydantic schema for OMOP table.

    Args:
        table_name: OMOP table name (lowercase with underscores).

    Returns:
        Pydantic model class or None if not found.
    """
    return OMOP_SCHEMAS.get(table_name)
