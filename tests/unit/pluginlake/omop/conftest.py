"""Shared test fixtures for OMOP module tests."""

from datetime import date

import duckdb
import polars as pl
import pytest

from pluginlake.omop.storage import (  # ty: ignore[unresolved-import]  # storage.py deleted; refactor pending
    register_vocabulary_tables,
    save_vocabulary_table,
)


@pytest.fixture
def sample_concepts() -> pl.DataFrame:
    """Sample OMOP concept data for testing."""
    return pl.DataFrame(
        {
            "concept_id": [8507, 8532, 201826, 320128, 4329847, 9201, 9202, 38000280, 8527, 8516],
            "concept_name": [
                "Male",
                "Female",
                "Type 2 diabetes mellitus",
                "Essential hypertension",
                "Myocardial infarction",
                "Inpatient Visit",
                "Outpatient Visit",
                "EHR",
                "White",
                "Black or African American",
            ],
            "domain_id": [
                "Gender",
                "Gender",
                "Condition",
                "Condition",
                "Condition",
                "Visit",
                "Visit",
                "Type Concept",
                "Race",
                "Race",
            ],
            "vocabulary_id": [
                "Gender",
                "Gender",
                "SNOMED",
                "SNOMED",
                "SNOMED",
                "Visit",
                "Visit",
                "Type Concept",
                "Race",
                "Race",
            ],
            "concept_class_id": [
                "Gender",
                "Gender",
                "Clinical Finding",
                "Clinical Finding",
                "Clinical Finding",
                "Visit",
                "Visit",
                "Type Concept",
                "Race",
                "Race",
            ],
            "standard_concept": ["S", "S", "S", "S", "S", "S", "S", "S", "S", "S"],
            "concept_code": [
                "M",
                "F",
                "44054006",
                "59621000",
                "22298006",
                "IP",
                "OP",
                "EHR",
                "White",
                "Black",
            ],
            "valid_start_date": [date(1970, 1, 1)] * 10,
            "valid_end_date": [date(2099, 12, 31)] * 10,
            "invalid_reason": [None] * 10,
        }
    )


@pytest.fixture
def sample_vocabularies() -> pl.DataFrame:
    """Sample OMOP vocabulary metadata for testing."""
    return pl.DataFrame(
        {
            "vocabulary_id": ["SNOMED", "Gender", "Race", "Visit", "Type Concept"],
            "vocabulary_name": [
                "SNOMED CT",
                "OMOP Gender",
                "OMOP Race",
                "OMOP Visit",
                "OMOP Type Concept",
            ],
            "vocabulary_reference": [
                "http://www.snomed.org/",
                "OMOP generated",
                "OMOP generated",
                "OMOP generated",
                "OMOP generated",
            ],
            "vocabulary_version": ["2024-01-01", None, None, None, None],
            "vocabulary_concept_id": [4180186, 44819147, 44819148, 44819149, 44819150],
        }
    )


@pytest.fixture
def sample_domains() -> pl.DataFrame:
    """Sample OMOP domain data for testing."""
    return pl.DataFrame(
        {
            "domain_id": ["Condition", "Gender", "Race", "Visit", "Type Concept"],
            "domain_name": ["Condition", "Gender", "Race", "Visit", "Type Concept"],
            "domain_concept_id": [19, 44819147, 44819148, 44819149, 44819150],
        }
    )


@pytest.fixture
def sample_concept_classes() -> pl.DataFrame:
    """Sample OMOP concept class data for testing."""
    return pl.DataFrame(
        {
            "concept_class_id": ["Clinical Finding", "Gender", "Race", "Visit", "Type Concept"],
            "concept_class_name": [
                "Clinical Finding",
                "Gender",
                "Race",
                "Visit",
                "Type Concept",
            ],
            "concept_class_concept_id": [0, 0, 0, 0, 0],
        }
    )


@pytest.fixture
def sample_concept_relationships() -> pl.DataFrame:
    """Sample OMOP concept relationship data for testing."""
    return pl.DataFrame(
        {
            "concept_id_1": [320128, 201826],
            "concept_id_2": [4329847, 4329847],
            "relationship_id": ["Subsumes", "Subsumes"],
            "valid_start_date": [date(1970, 1, 1), date(1970, 1, 1)],
            "valid_end_date": [date(2099, 12, 31), date(2099, 12, 31)],
            "invalid_reason": [None, None],
        }
    )


@pytest.fixture
def sample_concept_ancestor() -> pl.DataFrame:
    """Sample OMOP concept ancestor data for testing."""
    return pl.DataFrame(
        {
            "ancestor_concept_id": [320128, 320128, 201826],
            "descendant_concept_id": [320128, 4329847, 4329847],
            "min_levels_of_separation": [0, 1, 1],
            "max_levels_of_separation": [0, 1, 1],
        }
    )


@pytest.fixture
def sample_source_to_concept_map() -> pl.DataFrame:
    """Sample source to concept map data for testing."""
    return pl.DataFrame(
        {
            "source_code": ["E11", "I10", "I21.9"],
            "source_concept_id": [0, 0, 0],
            "source_vocabulary_id": ["ICD10CM", "ICD10CM", "ICD10CM"],
            "source_code_description": [
                "Type 2 diabetes mellitus",
                "Essential hypertension",
                "Acute myocardial infarction, unspecified",
            ],
            "target_concept_id": [201826, 320128, 4329847],
            "target_vocabulary_id": ["SNOMED", "SNOMED", "SNOMED"],
            "valid_start_date": [date(2015, 1, 1), date(2015, 1, 1), date(2015, 1, 1)],
            "valid_end_date": [date(2099, 12, 31), date(2099, 12, 31), date(2099, 12, 31)],
            "invalid_reason": [None, None, None],
        }
    )


@pytest.fixture
def test_db_with_vocabularies(
    tmp_path,
    sample_concepts,
    sample_vocabularies,
    sample_domains,
    sample_concept_classes,
    sample_concept_ancestor,
    sample_source_to_concept_map,
) -> duckdb.DuckDBPyConnection:
    """Create DuckDB connection with registered vocabulary tables."""
    vocab_dir = tmp_path / "vocabularies" / "parquet"
    vocab_dir.mkdir(parents=True, exist_ok=True)

    save_vocabulary_table(sample_concepts, "concept", output_dir=vocab_dir)
    save_vocabulary_table(sample_vocabularies, "vocabulary", output_dir=vocab_dir)
    save_vocabulary_table(sample_domains, "domain", output_dir=vocab_dir)
    save_vocabulary_table(sample_concept_classes, "concept_class", output_dir=vocab_dir)
    save_vocabulary_table(sample_concept_ancestor, "concept_ancestor", output_dir=vocab_dir)
    save_vocabulary_table(sample_source_to_concept_map, "source_to_concept_map", output_dir=vocab_dir)

    con = duckdb.connect(":memory:")
    register_vocabulary_tables(con, data_dir=vocab_dir)

    return con
