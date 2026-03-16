"""Tests for pluginlake.fhir.translator_registry."""

import pytest
from plugin_rosetta.translators.base import FhirToOmopTranslator

from pluginlake.fhir.translator_registry import (
    FHIR_RESOURCE_TYPES,
    FHIR_TO_OMOP_TABLE,
    OMOP_TABLE_TO_FHIR,
    OMOP_TARGET_TABLES,
    get_translator,
)


def test_all_resource_types_have_omop_mapping():
    for rt in FHIR_RESOURCE_TYPES:
        assert rt in FHIR_TO_OMOP_TABLE


def test_omop_table_to_fhir_is_consistent():
    for omop_table, fhir_types in OMOP_TABLE_TO_FHIR.items():
        for ft in fhir_types:
            assert FHIR_TO_OMOP_TABLE[ft] == omop_table


def test_omop_target_tables_sorted():
    assert sorted(OMOP_TARGET_TABLES) == OMOP_TARGET_TABLES


def test_get_translator_returns_instance():
    for rt in FHIR_RESOURCE_TYPES:
        translator = get_translator(rt)
        assert isinstance(translator, FhirToOmopTranslator)


def test_get_translator_raises_for_unknown():
    with pytest.raises(ValueError, match="Unsupported FHIR resource type"):
        get_translator("unknown_type")


def test_patient_translator_translates():
    translator = get_translator("patient")
    record = {
        "resourceType": "Patient",
        "id": "abc123",
        "birthDate": "1990-01-15",
        "gender": "male",
    }
    result = translator.translate_record(record)
    assert result["year_of_birth"] == 1990
    assert result["gender_source_value"] == "male"
