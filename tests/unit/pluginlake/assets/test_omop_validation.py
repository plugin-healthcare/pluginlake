"""Tests for OMOP vocabulary validation integration in clinical asset."""

from datetime import date
from unittest.mock import MagicMock, patch

import duckdb
import polars as pl
import pytest
from dagster import AssetKey

from pluginlake.assets.omop import omop_clinical_tables

_raw_fn = omop_clinical_tables.op.compute_fn.decorated_fn  # type: ignore[union-attr]


def _create_vocab_db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("ATTACH ':memory:' AS ducklake")
    conn.execute("CREATE SCHEMA ducklake.omop_vocab")

    concepts = pl.DataFrame(
        {
            "concept_id": [0, 8507, 8532, 9999],
            "concept_name": ["No matching concept", "Male", "Female", "Deprecated"],
            "domain_id": ["Metadata", "Gender", "Gender", "Gender"],
            "vocabulary_id": ["None", "Gender", "Gender", "Gender"],
            "concept_class_id": ["Undefined", "Gender", "Gender", "Gender"],
            "standard_concept": pl.Series([None, "S", "S", "S"], dtype=pl.Utf8),
            "concept_code": ["No matching concept", "M", "F", "X"],
            "valid_start_date": [date(1970, 1, 1)] * 4,
            "valid_end_date": [date(2099, 12, 31)] * 4,
            "invalid_reason": pl.Series([None, None, None, "D"], dtype=pl.Utf8),
        }
    )
    tmp = "_tmp_concept"
    conn.register(tmp, concepts.to_arrow())
    conn.execute(f"CREATE TABLE ducklake.omop_vocab.concept AS SELECT * FROM {tmp}")
    conn.unregister(tmp)
    return conn


def _build_context(asset_keys: list[AssetKey]) -> MagicMock:
    ctx = MagicMock()
    ctx.selected_asset_keys = set(asset_keys)
    return ctx


@pytest.fixture
def person_df():
    return pl.DataFrame(
        {
            "person_id": [1, 2],
            "gender_concept_id": [8507, 8532],
            "year_of_birth": [1990, 1985],
            "race_concept_id": [0, 0],
            "ethnicity_concept_id": [0, 0],
        }
    )


@pytest.fixture
def person_df_with_invalid():
    return pl.DataFrame(
        {
            "person_id": [1, 2, 3],
            "gender_concept_id": [8507, 9999, 777777],
            "year_of_birth": [1990, 1985, 2000],
            "race_concept_id": [0, 0, 0],
            "ethnicity_concept_id": [0, 0, 0],
        }
    )


def test_vocab_dependency_declared():
    deps = omop_clinical_tables.asset_deps
    concept_key = AssetKey(["omop_vocab", "concept"])
    all_dep_keys = set()
    for dep_set in deps.values():
        all_dep_keys.update(dep_set)
    assert concept_key in all_dep_keys


@patch("pluginlake.assets.omop.setup_ducklake")
@patch("pluginlake.assets.omop.load_omop_dataset")
@patch("pluginlake.assets.omop.get_omop_settings")
def test_validate_on_yields_with_metadata(mock_settings, mock_load, mock_setup, person_df_with_invalid):
    settings = MagicMock()
    settings.validate_concepts = True
    settings.vocabulary_schema = "omop_vocab"
    mock_settings.return_value = settings

    mock_load.return_value = {"person": person_df_with_invalid}

    conn = _create_vocab_db()
    mock_setup.return_value = conn

    context = _build_context([AssetKey(["omop", "person"])])

    outputs = list(_raw_fn(context))
    assert len(outputs) == 1
    output = outputs[0]
    assert output.output_name == "person"
    assert output.value.height == 3
    assert output.metadata["row_count"].value == 3
    assert output.metadata["invalid_concept_count"].value > 0
    assert "invalid_concepts" in output.metadata

    conn.close()


@patch("pluginlake.assets.omop.setup_ducklake")
@patch("pluginlake.assets.omop.load_omop_dataset")
@patch("pluginlake.assets.omop.get_omop_settings")
def test_validate_off_skips(mock_settings, mock_load, mock_setup, person_df):
    settings = MagicMock()
    settings.validate_concepts = False
    mock_settings.return_value = settings

    mock_load.return_value = {"person": person_df}

    context = _build_context([AssetKey(["omop", "person"])])

    outputs = list(_raw_fn(context))
    assert len(outputs) == 1
    mock_setup.assert_not_called()
    assert "invalid_concept_count" not in (outputs[0].metadata or {})


@patch("pluginlake.assets.omop.setup_ducklake")
@patch("pluginlake.assets.omop.load_omop_dataset")
@patch("pluginlake.assets.omop.get_omop_settings")
def test_valid_concepts_zero_invalid(mock_settings, mock_load, mock_setup, person_df):
    settings = MagicMock()
    settings.validate_concepts = True
    settings.vocabulary_schema = "omop_vocab"
    mock_settings.return_value = settings

    mock_load.return_value = {"person": person_df}

    conn = _create_vocab_db()
    mock_setup.return_value = conn

    context = _build_context([AssetKey(["omop", "person"])])

    outputs = list(_raw_fn(context))
    assert len(outputs) == 1
    output = outputs[0]
    assert output.metadata["invalid_concept_count"].value == 0
    assert "invalid_concepts" not in output.metadata

    conn.close()


@patch("pluginlake.assets.omop.setup_ducklake")
@patch("pluginlake.assets.omop.load_omop_dataset")
@patch("pluginlake.assets.omop.get_omop_settings")
def test_metadata_includes_invalid_summary(mock_settings, mock_load, mock_setup, person_df_with_invalid):
    settings = MagicMock()
    settings.validate_concepts = True
    settings.vocabulary_schema = "omop_vocab"
    mock_settings.return_value = settings

    mock_load.return_value = {"person": person_df_with_invalid}

    conn = _create_vocab_db()
    mock_setup.return_value = conn

    context = _build_context([AssetKey(["omop", "person"])])

    outputs = list(_raw_fn(context))
    output = outputs[0]
    invalid_concepts = output.metadata["invalid_concepts"].value
    assert isinstance(invalid_concepts, list)
    assert len(invalid_concepts) > 0
    entry = invalid_concepts[0]
    assert "column_name" in entry
    assert "sample_ids" in entry
    assert "count" in entry

    conn.close()
