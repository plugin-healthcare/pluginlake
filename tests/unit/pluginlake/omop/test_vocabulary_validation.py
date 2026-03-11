"""Tests for vocabulary validation functions."""

import polars as pl

from pluginlake.omop.vocabulary_validation import (
    filter_invalid_rows,
    validate_concept_ids,
    validate_table_concepts,
    write_audit_table,
)


def test_validate_concept_ids_all_valid(test_db_with_vocabularies):
    concept_ids = [8507, 8532, 201826]

    result = validate_concept_ids(test_db_with_vocabularies, concept_ids)

    assert result.height == 3
    assert all(result["is_valid"])
    assert all(result["validation_message"] == "Valid")


def test_validate_concept_ids_missing_concept(test_db_with_vocabularies):
    concept_ids = [8507, 999999]

    result = validate_concept_ids(test_db_with_vocabularies, concept_ids)

    assert result.height == 2
    valid_mask = result["is_valid"]
    assert valid_mask[0]
    assert not valid_mask[1]
    assert "does not exist" in result["validation_message"][1]


def test_validate_concept_ids_empty_list(test_db_with_vocabularies):
    result = validate_concept_ids(test_db_with_vocabularies, [])

    assert result.height == 0
    assert "concept_id" in result.columns
    assert "is_valid" in result.columns


def test_validate_concept_ids_with_domain_filter(test_db_with_vocabularies):
    concept_ids = [8507, 201826]

    result = validate_concept_ids(test_db_with_vocabularies, concept_ids, domain_id="Gender")

    assert result.height == 2
    assert result["is_valid"][0]
    assert not result["is_valid"][1]
    assert "Wrong domain" in result["validation_message"][1]


def test_validate_concept_ids_with_vocabulary_filter(test_db_with_vocabularies):
    concept_ids = [8507, 201826]

    result = validate_concept_ids(test_db_with_vocabularies, concept_ids, vocabulary_id="SNOMED")

    assert result.height == 2
    assert not result["is_valid"][0]
    assert result["is_valid"][1]
    assert "Wrong vocabulary" in result["validation_message"][0]


def test_validate_concept_ids_standard_only(test_db_with_vocabularies):
    concept_ids = [8507, 8532]

    result = validate_concept_ids(test_db_with_vocabularies, concept_ids, standard_only=True)

    assert result.height == 2
    assert all(result["is_valid"])


def test_validate_concept_ids_standard_only_false(test_db_with_vocabularies):
    concept_ids = [8507, 8532]

    result = validate_concept_ids(test_db_with_vocabularies, concept_ids, standard_only=False)

    assert result.height == 2
    assert all(result["is_valid"])


def test_validate_table_concepts_all_valid(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "condition_occurrence_id": [1, 2, 3],
            "person_id": [1, 2, 3],
            "condition_concept_id": [201826, 320128, 4329847],
            "condition_type_concept_id": [38000280, 38000280, 38000280],
        }
    )

    result = validate_table_concepts(test_db_with_vocabularies, df, "condition_occurrence")

    assert result.height >= 1
    assert all(result["is_valid"])


def test_validate_table_concepts_with_invalid(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "condition_occurrence_id": [1, 2],
            "person_id": [1, 2],
            "condition_concept_id": [201826, 999999],
            "condition_type_concept_id": [38000280, 38000280],
        }
    )

    result = validate_table_concepts(test_db_with_vocabularies, df, "condition_occurrence")

    assert result.height >= 1
    invalid = result.filter(~pl.col("is_valid"))
    assert invalid.height >= 1
    assert 999999 in invalid["concept_id"].to_list()


def test_validate_table_concepts_no_concept_columns(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "observation_period_id": [1, 2],
            "person_id": [1, 2],
        }
    )

    result = validate_table_concepts(test_db_with_vocabularies, df, "observation_period")

    assert result.height == 0


def test_validate_table_concepts_with_nulls(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "condition_occurrence_id": [1, 2, 3],
            "person_id": [1, 2, 3],
            "condition_concept_id": [201826, None, 320128],
            "condition_type_concept_id": [38000280, 38000280, 38000280],
        }
    )

    result = validate_table_concepts(test_db_with_vocabularies, df, "condition_occurrence")

    concept_ids = result["concept_id"].to_list()
    assert None not in concept_ids
    assert 201826 in concept_ids
    assert 320128 in concept_ids


def test_validate_table_concepts_unknown_table(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "id": [1, 2],
            "value": [100, 200],
        }
    )

    result = validate_table_concepts(test_db_with_vocabularies, df, "unknown_table")

    assert result.height == 0


def test_validate_table_concepts_multiple_columns(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "person_id": [1, 2],
            "gender_concept_id": [8507, 8532],
            "race_concept_id": [8527, 8516],
            "ethnicity_concept_id": [0, 0],
        }
    )

    result = validate_table_concepts(test_db_with_vocabularies, df, "person")

    assert result.height >= 4
    assert "gender_concept_id" in result["column_name"].to_list()
    assert "race_concept_id" in result["column_name"].to_list()
    assert "ethnicity_concept_id" in result["column_name"].to_list()


def test_validate_concept_ids_returns_concept_details(test_db_with_vocabularies):
    concept_ids = [8507, 201826]

    result = validate_concept_ids(test_db_with_vocabularies, concept_ids)

    assert "concept_name" in result.columns
    assert "domain_id" in result.columns
    assert "vocabulary_id" in result.columns
    assert result["concept_name"][0] == "Male"
    assert result["concept_name"][1] == "Type 2 diabetes mellitus"


def test_filter_invalid_rows_all_valid(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "condition_occurrence_id": [1, 2, 3],
            "person_id": [1, 2, 3],
            "condition_concept_id": [201826, 320128, 4329847],
            "condition_type_concept_id": [38000280, 38000280, 38000280],
        }
    )
    result = validate_table_concepts(test_db_with_vocabularies, df, "condition_occurrence")

    valid_df, invalid_df = filter_invalid_rows(df, result, "condition_occurrence")

    assert valid_df.height == 3
    assert invalid_df.height == 0


def test_filter_invalid_rows_some_invalid(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "condition_occurrence_id": [1, 2, 3],
            "person_id": [1, 2, 3],
            "condition_concept_id": [201826, 999999, 320128],
            "condition_type_concept_id": [38000280, 38000280, 38000280],
        }
    )
    result = validate_table_concepts(test_db_with_vocabularies, df, "condition_occurrence")

    valid_df, invalid_df = filter_invalid_rows(df, result, "condition_occurrence")

    assert valid_df.height == 2
    assert invalid_df.height == 1
    assert invalid_df["condition_concept_id"][0] == 999999


def test_filter_invalid_rows_multiple_columns(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "condition_occurrence_id": [1, 2],
            "person_id": [1, 2],
            "condition_concept_id": [201826, 320128],
            "condition_type_concept_id": [38000280, 888888],
        }
    )
    result = validate_table_concepts(test_db_with_vocabularies, df, "condition_occurrence")

    valid_df, invalid_df = filter_invalid_rows(df, result, "condition_occurrence")

    assert valid_df.height == 1
    assert invalid_df.height == 1
    assert invalid_df["condition_type_concept_id"][0] == 888888


def test_filter_invalid_rows_nulls_are_valid(test_db_with_vocabularies):
    df = pl.DataFrame(
        {
            "condition_occurrence_id": [1, 2, 3],
            "person_id": [1, 2, 3],
            "condition_concept_id": [201826, None, 320128],
            "condition_type_concept_id": [38000280, 38000280, 38000280],
        }
    )
    result = validate_table_concepts(test_db_with_vocabularies, df, "condition_occurrence")

    valid_df, invalid_df = filter_invalid_rows(df, result, "condition_occurrence")

    assert valid_df.height == 3
    assert invalid_df.height == 0


def test_filter_invalid_rows_empty_validation():
    df = pl.DataFrame(
        {
            "id": [1, 2],
            "value": [10, 20],
        }
    )
    empty_result = pl.DataFrame(
        schema={
            "column_name": pl.Utf8,
            "concept_id": pl.Int64,
            "is_valid": pl.Boolean,
            "validation_message": pl.Utf8,
        }
    )

    valid_df, invalid_df = filter_invalid_rows(df, empty_result, "test")

    assert valid_df.height == 2
    assert invalid_df.height == 0


def test_write_audit_table(test_db_with_vocabularies):
    audit_data = pl.DataFrame(
        {
            "column_name": ["condition_concept_id", "condition_concept_id"],
            "concept_id": [201826, 999999],
            "is_valid": [True, False],
            "validation_message": ["Valid", "Concept ID does not exist"],
        }
    )

    write_audit_table(test_db_with_vocabularies, audit_data, "condition_occurrence")

    result = test_db_with_vocabularies.sql("SELECT * FROM ducklake.omop_audit.condition_occurrence").pl()
    assert result.height == 2
    assert "is_valid" in result.columns


def test_write_audit_table_empty(test_db_with_vocabularies):
    empty = pl.DataFrame(
        schema={
            "column_name": pl.Utf8,
            "concept_id": pl.Int64,
            "is_valid": pl.Boolean,
            "validation_message": pl.Utf8,
        }
    )

    write_audit_table(test_db_with_vocabularies, empty, "condition_occurrence")

    tables = test_db_with_vocabularies.sql(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'omop_audit'"
    ).fetchall()
    assert len(tables) == 0
