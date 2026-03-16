"""FHIR-to-OMOP translator registry.

Maps FHIR R4 resource types to their plugin-rosetta translators and
the corresponding OMOP CDM target tables.
"""

from plugin_rosetta.translators.base import FhirToOmopTranslator
from plugin_rosetta.translators.fhir_to_omop.allergy import AllergyTranslator
from plugin_rosetta.translators.fhir_to_omop.condition import ConditionTranslator
from plugin_rosetta.translators.fhir_to_omop.encounter import EncounterTranslator
from plugin_rosetta.translators.fhir_to_omop.immunization import ImmunizationTranslator
from plugin_rosetta.translators.fhir_to_omop.medication import MedicationTranslator
from plugin_rosetta.translators.fhir_to_omop.observation import ObservationTranslator
from plugin_rosetta.translators.fhir_to_omop.patient import PatientTranslator
from plugin_rosetta.translators.fhir_to_omop.procedure import ProcedureTranslator

FHIR_RESOURCE_TYPES: list[str] = [
    "patient",
    "encounter",
    "condition",
    "observation",
    "procedure",
    "medication_statement",
    "immunization",
    "allergy_intolerance",
]

FHIR_TO_OMOP_TABLE: dict[str, str] = {
    "patient": "person",
    "encounter": "visit_occurrence",
    "condition": "condition_occurrence",
    "observation": "observation",
    "procedure": "procedure_occurrence",
    "medication_statement": "drug_exposure",
    "immunization": "drug_exposure",
    "allergy_intolerance": "observation",
}

OMOP_TABLE_TO_FHIR: dict[str, list[str]] = {}
for _fhir, _omop in FHIR_TO_OMOP_TABLE.items():
    OMOP_TABLE_TO_FHIR.setdefault(_omop, []).append(_fhir)

OMOP_TARGET_TABLES: list[str] = sorted(OMOP_TABLE_TO_FHIR)

_TRANSLATOR_MAP: dict[str, type[FhirToOmopTranslator]] = {
    "patient": PatientTranslator,
    "encounter": EncounterTranslator,
    "condition": ConditionTranslator,
    "observation": ObservationTranslator,
    "procedure": ProcedureTranslator,
    "medication_statement": MedicationTranslator,
    "immunization": ImmunizationTranslator,
    "allergy_intolerance": AllergyTranslator,
}


def get_translator(resource_type: str) -> FhirToOmopTranslator:
    """Return a translator instance for the given FHIR resource type.

    Args:
        resource_type: Lowercase FHIR resource type (e.g. ``patient``).

    Returns:
        An instantiated translator.

    Raises:
        ValueError: If the resource type is not supported.
    """
    cls = _TRANSLATOR_MAP.get(resource_type)
    if cls is None:
        msg = f"Unsupported FHIR resource type: {resource_type!r}. Supported: {FHIR_RESOURCE_TYPES}"
        raise ValueError(msg)
    return cls()
