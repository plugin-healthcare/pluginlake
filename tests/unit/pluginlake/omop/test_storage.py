"""Tests for OMOP storage module."""

import polars as pl
import pytest

from pluginlake.omop.storage import (
    get_duckdb_connection,
    load_parquet_as_polars,
    query_duckdb,
    register_omop_tables,
    save_omop_table,
)


def test_save_omop_table_creates_parquet(tmp_path):
    """Test saving DataFrame as Parquet file."""
    df = pl.DataFrame(
        {
            "person_id": [1, 2, 3],
            "year_of_birth": [1980, 1990, 2000],
        }
    )

    output_path = save_omop_table(df, "person", output_dir=tmp_path)

    assert output_path.exists()
    assert output_path.name == "person.parquet"
    assert output_path.parent == tmp_path


def test_save_omop_table_raises_if_exists(tmp_path):
    """Test error when file already exists and overwrite=False."""
    df = pl.DataFrame({"person_id": [1], "year_of_birth": [1980]})

    save_omop_table(df, "person", output_dir=tmp_path)

    with pytest.raises(FileExistsError):
        save_omop_table(df, "person", output_dir=tmp_path, overwrite=False)


def test_save_omop_table_overwrites_when_allowed(tmp_path):
    """Test overwriting existing file when overwrite=True."""
    df1 = pl.DataFrame({"person_id": [1], "year_of_birth": [1980]})
    df2 = pl.DataFrame({"person_id": [1, 2], "year_of_birth": [1980, 1990]})

    save_omop_table(df1, "person", output_dir=tmp_path)
    output_path = save_omop_table(df2, "person", output_dir=tmp_path, overwrite=True)

    loaded_df = pl.read_parquet(output_path)
    expected_row_count = 2
    assert len(loaded_df) == expected_row_count


def test_get_duckdb_connection_in_memory():
    """Test creating in-memory DuckDB connection."""
    con = get_duckdb_connection()

    assert con is not None
    result = con.execute("SELECT 1 as value").fetchone()
    assert result is not None
    assert result[0] == 1


def test_get_duckdb_connection_with_file(tmp_path):
    """Test creating file-based DuckDB connection."""
    db_path = tmp_path / "test.duckdb"

    con = get_duckdb_connection(db_path)

    assert con is not None
    assert db_path.exists()


def test_register_omop_tables(tmp_path):
    """Test registering Parquet files as DuckDB views."""
    # Create test Parquet files
    df_person = pl.DataFrame({"person_id": [1, 2], "year_of_birth": [1980, 1990]})
    df_condition = pl.DataFrame({"condition_id": [1, 2], "person_id": [1, 2]})

    save_omop_table(df_person, "person", output_dir=tmp_path)
    save_omop_table(df_condition, "condition_occurrence", output_dir=tmp_path)

    # Register tables
    con = get_duckdb_connection()
    registered = register_omop_tables(con, data_dir=tmp_path)

    assert "person" in registered
    assert "condition_occurrence" in registered

    # Query registered table
    result = con.execute("SELECT COUNT(*) FROM person").fetchone()
    assert result is not None
    expected_count = 2
    assert result[0] == expected_count


def test_register_omop_tables_specific_tables(tmp_path):
    """Test registering only specific tables."""
    df_person = pl.DataFrame({"person_id": [1, 2]})
    df_condition = pl.DataFrame({"condition_id": [1, 2]})

    save_omop_table(df_person, "person", output_dir=tmp_path)
    save_omop_table(df_condition, "condition_occurrence", output_dir=tmp_path)

    con = get_duckdb_connection()
    registered = register_omop_tables(con, data_dir=tmp_path, table_names=["person"])

    assert "person" in registered
    assert "condition_occurrence" not in registered


def test_load_parquet_as_polars(tmp_path):
    """Test loading Parquet file as Polars DataFrame."""
    df = pl.DataFrame({"person_id": [1, 2, 3], "year_of_birth": [1980, 1990, 2000]})

    save_omop_table(df, "person", output_dir=tmp_path)

    loaded_df = load_parquet_as_polars("person", data_dir=tmp_path)

    expected_row_count = 3
    assert len(loaded_df) == expected_row_count
    assert "person_id" in loaded_df.columns
    assert loaded_df["person_id"].to_list() == [1, 2, 3]


def test_load_parquet_as_polars_file_not_found(tmp_path):
    """Test error when Parquet file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        load_parquet_as_polars("nonexistent", data_dir=tmp_path)


def test_query_duckdb(tmp_path):
    """Test executing SQL query via DuckDB."""
    df = pl.DataFrame(
        {
            "person_id": [1, 2, 3],
            "year_of_birth": [1980, 1990, 2000],
        }
    )

    save_omop_table(df, "person", output_dir=tmp_path)

    con = get_duckdb_connection()
    register_omop_tables(con, data_dir=tmp_path)

    result = query_duckdb(con, "SELECT * FROM person WHERE year_of_birth > 1985")

    expected_row_count = 2
    assert len(result) == expected_row_count
    assert result["year_of_birth"].to_list() == [1990, 2000]


def test_query_duckdb_with_aggregation(tmp_path):
    """Test SQL aggregation query."""
    df = pl.DataFrame(
        {
            "person_id": [1, 2, 3],
            "year_of_birth": [1980, 1990, 2000],
        }
    )

    save_omop_table(df, "person", output_dir=tmp_path)

    con = get_duckdb_connection()
    register_omop_tables(con, data_dir=tmp_path)

    result = query_duckdb(con, "SELECT AVG(year_of_birth) as avg_year FROM person")

    expected_avg = 1990.0
    assert result["avg_year"][0] == expected_avg
