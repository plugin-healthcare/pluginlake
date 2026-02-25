"""Tests for the DuckLake IO manager."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from dagster import AssetKey

from pluginlake.core.ducklake.io_manager import (
    CATALOG,
    DEFAULT_SCHEMA,
    DuckLakeIOManager,
)


@pytest.fixture
def mock_conn():
    """Provide a mock DuckDB connection."""
    return MagicMock()


@pytest.fixture
def io_mgr(mock_conn):
    """Provide a DuckLakeIOManager with a mock connection."""
    return DuckLakeIOManager(mock_conn)


@pytest.fixture
def io_mgr_mapped(mock_conn):
    """Provide a DuckLakeIOManager with schema mapping."""
    return DuckLakeIOManager(mock_conn, schema_mapping={"raw": "bronze"})


# --- _table_ref ---


def test_single_segment_key_uses_default_schema(io_mgr):
    ref = io_mgr.table_ref(["condition_era"])
    assert ref == f"{CATALOG}.{DEFAULT_SCHEMA}.condition_era"


def test_two_segment_key_uses_prefix_as_schema(io_mgr):
    ref = io_mgr.table_ref(["omop", "condition_era"])
    assert ref == f"{CATALOG}.omop.condition_era"


def test_three_segment_key_joins_remaining_with_underscore(io_mgr):
    ref = io_mgr.table_ref(["raw", "omop", "condition_era"])
    assert ref == f"{CATALOG}.raw.omop_condition_era"


def test_schema_mapping_overrides_prefix(io_mgr_mapped):
    ref = io_mgr_mapped.table_ref(["raw", "omop", "condition_era"])
    assert ref == f"{CATALOG}.bronze.omop_condition_era"


def test_schema_mapping_passthrough_when_not_mapped(io_mgr_mapped):
    ref = io_mgr_mapped.table_ref(["curated", "omop", "condition_era"])
    assert ref == f"{CATALOG}.curated.omop_condition_era"


# --- resolve_schema ---


def test_resolve_schema_mapped(io_mgr_mapped):
    assert io_mgr_mapped.resolve_schema("raw") == "bronze"


def test_resolve_schema_unmapped(io_mgr_mapped):
    assert io_mgr_mapped.resolve_schema("curated") == "curated"


# --- handle_output ---


def test_handle_output_creates_schema_and_table(mock_conn, io_mgr):
    context = MagicMock()
    context.asset_key = AssetKey(["omop", "condition_era"])

    df = pl.DataFrame({"id": [1, 2], "name": ["a", "b"]})
    io_mgr.handle_output(context, df)

    # Schema creation
    mock_conn.execute.assert_any_call(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.omop")

    # Data registration and table creation
    mock_conn.register.assert_called_once_with("_data", df)
    mock_conn.execute.assert_any_call(f"CREATE OR REPLACE TABLE {CATALOG}.omop.condition_era AS SELECT * FROM _data")
    mock_conn.unregister.assert_called_once_with("_data")


def test_handle_output_single_segment_uses_main(mock_conn, io_mgr):
    context = MagicMock()
    context.asset_key = AssetKey(["titanic_raw"])

    df = pl.DataFrame({"survived": [True, False]})
    io_mgr.handle_output(context, df)

    mock_conn.execute.assert_any_call(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{DEFAULT_SCHEMA}")
    mock_conn.execute.assert_any_call(
        f"CREATE OR REPLACE TABLE {CATALOG}.{DEFAULT_SCHEMA}.titanic_raw AS SELECT * FROM _data"
    )


# --- load_input ---


def test_load_input_returns_polars_lazyframe(mock_conn, io_mgr):
    context = MagicMock()
    context.asset_key = AssetKey(["omop", "condition_era"])

    expected = pl.DataFrame({"id": [1, 2], "name": ["a", "b"]}).lazy()
    mock_conn.sql.return_value.pl.return_value = expected

    result = io_mgr.load_input(context)

    mock_conn.sql.assert_called_once_with(f"SELECT * FROM {CATALOG}.omop.condition_era")
    assert isinstance(result, pl.LazyFrame)
    assert result.collect().shape == (2, 2)


def test_load_input_single_segment_key(mock_conn, io_mgr):
    context = MagicMock()
    context.asset_key = AssetKey(["titanic_raw"])

    expected = pl.DataFrame({"survived": [True]}).lazy()
    mock_conn.sql.return_value.pl.return_value = expected

    result = io_mgr.load_input(context)

    mock_conn.sql.assert_called_once_with(f"SELECT * FROM {CATALOG}.{DEFAULT_SCHEMA}.titanic_raw")
    assert isinstance(result, pl.LazyFrame)
