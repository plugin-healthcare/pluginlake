"""Integration test with Synthea OMOP dataset.

Tests the complete pipeline:
1. Load CSV files from Synthea 1k dataset
2. Validate schemas
3. Save to Parquet format
4. Query with DuckDB
5. Verify results
"""

from pathlib import Path

import polars as pl
import pytest

from pluginlake.omop import (
    get_cohort,
    get_conditions_for_person,
    get_duckdb_connection,
    get_measurement_values,
    get_observations_for_person,
    get_persons,
    get_visits_for_person,
    load_omop_table,
    register_omop_tables,
    save_omop_table,
)


@pytest.fixture(scope="module")
def synthea_data_dir() -> Path:
    """Path to Synthea 1k dataset."""
    data_dir = Path(__file__).parents[2] / "data" / "synthea" / "omop" / "synthea1k"
    if not data_dir.exists():
        pytest.skip(f"Synthea data not found at {data_dir}")
    return data_dir


@pytest.fixture(scope="module")
def parquet_output_dir(tmp_path_factory) -> Path:
    """Temporary directory for Parquet output."""
    return tmp_path_factory.mktemp("omop_parquet")


@pytest.fixture(scope="module")
def loaded_tables(synthea_data_dir: Path, parquet_output_dir: Path) -> dict[str, pl.DataFrame]:
    """Load all available Synthea tables and save to Parquet.

    Returns:
        Dictionary mapping table names to loaded DataFrames.
    """
    tables = {}

    available_tables = [
        "person",
        "observation_period",
        "visit_occurrence",
        "condition_occurrence",
        "procedure_occurrence",
        "drug_exposure",
        "measurement",
        "observation",
    ]

    for table_name in available_tables:
        csv_path = synthea_data_dir / f"{table_name}.csv"
        if not csv_path.exists():
            continue

        df = load_omop_table(
            csv_path,
            table_name=table_name,
            validate=False,
        )

        save_omop_table(
            df,
            table_name=table_name,
            output_dir=parquet_output_dir,
            overwrite=True,
        )

        tables[table_name] = df

    return tables


@pytest.fixture(scope="module")
def duckdb_con(parquet_output_dir: Path):
    """DuckDB connection with registered OMOP tables."""
    con = get_duckdb_connection()
    register_omop_tables(con, data_dir=parquet_output_dir)
    yield con
    con.close()


def test_load_person_table(loaded_tables: dict[str, pl.DataFrame]):
    """Test person table loads correctly."""
    assert "person" in loaded_tables
    df = loaded_tables["person"]

    assert len(df) > 0, "Person table should have records"
    assert "person_id" in df.columns
    assert "gender_concept_id" in df.columns
    assert "year_of_birth" in df.columns
    assert "race_concept_id" in df.columns
    assert "ethnicity_concept_id" in df.columns


def test_load_condition_table(loaded_tables: dict[str, pl.DataFrame]):
    """Test condition_occurrence table loads correctly."""
    assert "condition_occurrence" in loaded_tables
    df = loaded_tables["condition_occurrence"]

    assert len(df) > 0
    assert "condition_occurrence_id" in df.columns
    assert "person_id" in df.columns
    assert "condition_concept_id" in df.columns
    assert "condition_start_date" in df.columns


def test_load_measurement_table(loaded_tables: dict[str, pl.DataFrame]):
    """Test measurement table loads correctly."""
    assert "measurement" in loaded_tables
    df = loaded_tables["measurement"]

    assert len(df) > 0
    assert "measurement_id" in df.columns
    assert "person_id" in df.columns
    assert "measurement_concept_id" in df.columns
    assert "measurement_date" in df.columns


def test_query_all_persons(duckdb_con, loaded_tables: dict[str, pl.DataFrame]):
    """Test querying all persons."""
    result = get_persons(con=duckdb_con)

    expected_count = len(loaded_tables["person"])
    assert len(result) == expected_count
    assert "person_id" in result.columns


def test_query_persons_with_gender_filter(duckdb_con):
    """Test querying persons filtered by gender."""
    male_concept_id = 8507
    result = get_persons(con=duckdb_con, gender_concept_id=male_concept_id)

    assert len(result) > 0
    assert all(result["gender_concept_id"] == male_concept_id)


def test_query_persons_with_year_range(duckdb_con):
    """Test querying persons with birth year range."""
    result = get_persons(
        con=duckdb_con,
        year_of_birth_min=1950,
        year_of_birth_max=2000,
    )

    assert len(result) > 0
    assert all(result["year_of_birth"] >= 1950)
    assert all(result["year_of_birth"] <= 2000)


def test_query_persons_with_limit(duckdb_con):
    """Test querying persons with limit."""
    limit_count = 10
    result = get_persons(con=duckdb_con, limit=limit_count)

    assert len(result) == limit_count


def test_query_conditions_for_person(duckdb_con, loaded_tables: dict[str, pl.DataFrame]):
    """Test querying conditions for a specific person."""
    person_df = loaded_tables["person"]
    test_person_id = person_df["person_id"][0]

    result = get_conditions_for_person(test_person_id, con=duckdb_con)

    assert len(result) >= 0
    if len(result) > 0:
        assert all(result["person_id"] == test_person_id)
        assert "condition_concept_id" in result.columns


def test_query_observations_for_person(duckdb_con, loaded_tables: dict[str, pl.DataFrame]):
    """Test querying observations for a specific person."""
    obs_df = loaded_tables.get("observation")
    if obs_df is None or len(obs_df) == 0:
        pytest.skip("No observations in dataset")

    test_person_id = obs_df["person_id"][0]
    result = get_observations_for_person(test_person_id, con=duckdb_con)

    assert len(result) > 0
    assert all(result["person_id"] == test_person_id)


def test_query_visits_for_person(duckdb_con, loaded_tables: dict[str, pl.DataFrame]):
    """Test querying visits for a specific person."""
    visit_df = loaded_tables["visit_occurrence"]
    test_person_id = visit_df["person_id"][0]

    result = get_visits_for_person(test_person_id, con=duckdb_con)

    assert len(result) > 0
    assert all(result["person_id"] == test_person_id)
    assert "visit_concept_id" in result.columns


def test_query_measurement_values(duckdb_con, loaded_tables: dict[str, pl.DataFrame]):
    """Test querying measurement values for a person."""
    meas_df = loaded_tables["measurement"]
    test_person_id = meas_df["person_id"][0]
    test_concept_id = meas_df["measurement_concept_id"][0]

    result = get_measurement_values(
        test_person_id,
        test_concept_id,
        con=duckdb_con,
    )

    assert len(result) > 0
    assert all(result["person_id"] == test_person_id)
    assert all(result["measurement_concept_id"] == test_concept_id)


def test_query_cohort_with_condition(duckdb_con, loaded_tables: dict[str, pl.DataFrame]):
    """Test selecting cohort with specific condition."""
    cond_df = loaded_tables["condition_occurrence"]
    test_condition_id = cond_df["condition_concept_id"][0]

    result = get_cohort(
        con=duckdb_con,
        has_condition_concept_id=test_condition_id,
    )

    assert len(result) > 0
    assert "person_id" in result.columns


def test_query_cohort_with_age_range(duckdb_con):
    """Test selecting cohort with age range."""
    result = get_cohort(
        con=duckdb_con,
        min_age=30,
        max_age=60,
    )

    assert len(result) >= 0
    if len(result) > 0:
        current_year = 2026
        assert all(result["year_of_birth"] <= current_year - 30)
        assert all(result["year_of_birth"] >= current_year - 60)


def test_parquet_files_created(parquet_output_dir: Path):
    """Test that Parquet files were created correctly."""
    parquet_files = list(parquet_output_dir.glob("*.parquet"))

    assert len(parquet_files) > 0, "Should create at least one Parquet file"

    for parquet_file in parquet_files:
        assert parquet_file.stat().st_size > 0, f"{parquet_file.name} should not be empty"
