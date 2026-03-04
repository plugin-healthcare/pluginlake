"""Tests for OMOP validation module."""

import polars as pl

from pluginlake.omop.validation import ValidationError, validate_omop_table_schema


def test_validation_error_repr():
    """Test ValidationError string representation."""
    error = ValidationError("person_id", "Missing column")
    assert "column=person_id" in repr(error)
    assert "Missing column" in repr(error)


def test_validation_error_with_row_index():
    """Test ValidationError with row index."""
    error = ValidationError("year_of_birth", "Invalid value", row_index=42)
    assert "row=42" in repr(error)
    assert "column=year_of_birth" in repr(error)


def test_validate_person_table_valid():
    """Test validation passes for valid person table."""
    df = pl.DataFrame(
        {
            "person_id": [1, 2, 3],
            "gender_concept_id": [8507, 8532, 8507],
            "year_of_birth": [1980, 1990, 1975],
            "month_of_birth": [1, 6, 12],
            "day_of_birth": [15, 20, 5],
            "race_concept_id": [8527, 8516, 8527],
            "ethnicity_concept_id": [0, 0, 0],
            "location_id": [None, None, None],
            "provider_id": [None, None, None],
            "care_site_id": [None, None, None],
            "person_source_value": ["P1", "P2", "P3"],
            "gender_source_value": ["M", "F", "M"],
            "gender_source_concept_id": [0, 0, 0],
            "race_source_value": ["white", "black", "white"],
            "race_source_concept_id": [0, 0, 0],
            "ethnicity_source_value": ["hispanic", "hispanic", "not hispanic"],
            "ethnicity_source_concept_id": [0, 0, 0],
        }
    )

    errors = validate_omop_table_schema(df, "person")
    assert len(errors) == 0


def test_validate_missing_required_column():
    """Test validation detects missing required columns."""
    df = pl.DataFrame(
        {
            "person_id": [1, 2, 3],
            "gender_concept_id": [8507, 8532, 8507],
        }
    )

    errors = validate_omop_table_schema(df, "person")

    assert len(errors) > 0
    missing_errors = [e for e in errors if "missing" in e.message.lower()]
    assert len(missing_errors) > 0


def test_validate_unexpected_column():
    """Test validation detects unexpected columns."""
    df = pl.DataFrame(
        {
            "person_id": [1, 2, 3],
            "gender_concept_id": [8507, 8532, 8507],
            "year_of_birth": [1980, 1990, 1975],
            "month_of_birth": [1, 6, 12],
            "day_of_birth": [15, 20, 5],
            "race_concept_id": [8527, 8516, 8527],
            "ethnicity_concept_id": [0, 0, 0],
            "location_id": [None, None, None],
            "provider_id": [None, None, None],
            "care_site_id": [None, None, None],
            "person_source_value": ["P1", "P2", "P3"],
            "gender_source_value": ["M", "F", "M"],
            "gender_source_concept_id": [0, 0, 0],
            "race_source_value": ["white", "black", "white"],
            "race_source_concept_id": [0, 0, 0],
            "ethnicity_source_value": ["hispanic", "hispanic", "not hispanic"],
            "ethnicity_source_concept_id": [0, 0, 0],
            "extra_column": ["A", "B", "C"],
        }
    )

    errors = validate_omop_table_schema(df, "person")

    unexpected_errors = [e for e in errors if e.column == "extra_column"]
    assert len(unexpected_errors) == 1
    assert "unexpected" in unexpected_errors[0].message.lower()


def test_validate_type_mismatch():
    """Test validation detects type mismatches."""
    df = pl.DataFrame(
        {
            "person_id": ["not_an_int", "also_not_int", "still_not_int"],
            "gender_concept_id": [8507, 8532, 8507],
            "year_of_birth": [1980, 1990, 1975],
            "month_of_birth": [1, 6, 12],
            "day_of_birth": [15, 20, 5],
            "race_concept_id": [8527, 8516, 8527],
            "ethnicity_concept_id": [0, 0, 0],
            "location_id": [None, None, None],
            "provider_id": [None, None, None],
            "care_site_id": [None, None, None],
            "person_source_value": ["P1", "P2", "P3"],
            "gender_source_value": ["M", "F", "M"],
            "gender_source_concept_id": [0, 0, 0],
            "race_source_value": ["white", "black", "white"],
            "race_source_concept_id": [0, 0, 0],
            "ethnicity_source_value": ["hispanic", "hispanic", "not hispanic"],
            "ethnicity_source_concept_id": [0, 0, 0],
        }
    )

    errors = validate_omop_table_schema(df, "person")

    type_errors = [e for e in errors if "type mismatch" in e.message.lower()]
    assert len(type_errors) > 0


def test_validate_unknown_table():
    """Test validation handles unknown table names gracefully."""
    df = pl.DataFrame({"col1": [1, 2, 3]})

    errors = validate_omop_table_schema(df, "unknown_table")

    assert len(errors) == 0


def test_validate_condition_occurrence_valid():
    """Test validation passes for valid condition_occurrence table."""
    df = pl.DataFrame(
        {
            "condition_occurrence_id": [1, 2, 3],
            "person_id": [100, 200, 300],
            "condition_concept_id": [320128, 320128, 201826],
            "condition_start_date": pl.Series(["2020-01-01", "2020-02-15", "2020-03-20"]).str.to_date(),
            "condition_type_concept_id": [32020, 32020, 32020],
            "condition_status_concept_id": [None, None, None],
            "stop_reason": [None, None, None],
            "provider_id": [None, None, None],
            "visit_occurrence_id": [None, None, None],
            "visit_detail_id": [None, None, None],
            "condition_source_value": ["Z99.89", "Z99.89", "E11.9"],
            "condition_source_concept_id": [0, 0, 0],
            "condition_status_source_value": [None, None, None],
        }
    )

    errors = validate_omop_table_schema(df, "condition_occurrence")
    assert len(errors) == 0
