"""Tests for OMOP query API."""

from datetime import date

import duckdb
import polars as pl
import pytest

from pluginlake.omop.queries import (
    get_cohort,
    get_conditions_for_person,
    get_measurement_values,
    get_observations_for_person,
    get_persons,
    get_visits_for_person,
)
from pluginlake.omop.storage import register_omop_tables, save_omop_table


@pytest.fixture
def sample_persons() -> pl.DataFrame:
    """Sample person data for testing."""
    return pl.DataFrame(
        {
            "person_id": [1, 2, 3, 4, 5],
            "gender_concept_id": [8507, 8532, 8507, 8532, 8507],
            "year_of_birth": [1980, 1990, 1975, 1985, 1995],
            "race_concept_id": [8527, 8516, 8527, 8527, 8516],
            "ethnicity_concept_id": [0, 0, 38003564, 0, 38003564],
        }
    )


@pytest.fixture
def sample_conditions() -> pl.DataFrame:
    """Sample condition occurrence data for testing."""
    return pl.DataFrame(
        {
            "condition_occurrence_id": [1, 2, 3, 4],
            "person_id": [1, 1, 2, 3],
            "condition_concept_id": [320128, 201826, 320128, 4329847],
            "condition_start_date": pl.Series(
                [
                    "2020-01-01",
                    "2020-06-15",
                    "2019-03-20",
                    "2021-12-01",
                ]
            ).str.to_date(),
        }
    )


@pytest.fixture
def sample_observations() -> pl.DataFrame:
    """Sample observation data for testing."""
    return pl.DataFrame(
        {
            "observation_id": [1, 2, 3],
            "person_id": [1, 2, 2],
            "observation_concept_id": [4013886, 4013886, 4265453],
            "observation_date": pl.Series(
                [
                    "2020-01-15",
                    "2020-02-20",
                    "2020-03-10",
                ]
            ).str.to_date(),
            "observation_type_concept_id": [38000280, 38000280, 38000280],
        }
    )


@pytest.fixture
def sample_visits() -> pl.DataFrame:
    """Sample visit occurrence data for testing."""
    return pl.DataFrame(
        {
            "visit_occurrence_id": [1, 2, 3],
            "person_id": [1, 1, 2],
            "visit_concept_id": [9201, 9201, 9202],
            "visit_start_date": pl.Series(
                [
                    "2020-01-01",
                    "2020-06-01",
                    "2020-03-15",
                ]
            ).str.to_date(),
            "visit_end_date": pl.Series(
                [
                    "2020-01-03",
                    "2020-06-02",
                    "2020-03-16",
                ]
            ).str.to_date(),
            "visit_type_concept_id": [44818518, 44818518, 44818518],
        }
    )


@pytest.fixture
def sample_measurements() -> pl.DataFrame:
    """Sample measurement data for testing."""
    return pl.DataFrame(
        {
            "measurement_id": [1, 2, 3, 4],
            "person_id": [1, 1, 1, 2],
            "measurement_concept_id": [3004249, 3004249, 3004249, 3004249],
            "measurement_date": pl.Series(
                [
                    "2020-01-01",
                    "2020-03-01",
                    "2020-06-01",
                    "2020-02-15",
                ]
            ).str.to_date(),
            "measurement_type_concept_id": [44818702, 44818702, 44818702, 44818702],
            "value_as_number": [120.5, 125.0, 118.0, 130.5],
        }
    )


@pytest.fixture
def sample_drug_exposures() -> pl.DataFrame:
    """Sample drug exposure data for testing."""
    return pl.DataFrame(
        {
            "drug_exposure_id": [1, 2, 3],
            "person_id": [1, 2, 3],
            "drug_concept_id": [1545958, 1545958, 1308216],
            "drug_exposure_start_date": pl.Series(
                [
                    "2020-01-01",
                    "2020-02-01",
                    "2020-03-01",
                ]
            ).str.to_date(),
            "drug_type_concept_id": [38000177, 38000177, 38000177],
        }
    )


@pytest.fixture
def test_db_with_data(
    tmp_path,
    sample_persons,
    sample_conditions,
    sample_observations,
    sample_visits,
    sample_measurements,
    sample_drug_exposures,
):
    """Create test database with sample data."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()

    save_omop_table(sample_persons, "person", output_dir=data_dir, overwrite=True)
    save_omop_table(sample_conditions, "condition_occurrence", output_dir=data_dir, overwrite=True)
    save_omop_table(sample_observations, "observation", output_dir=data_dir, overwrite=True)
    save_omop_table(sample_visits, "visit_occurrence", output_dir=data_dir, overwrite=True)
    save_omop_table(sample_measurements, "measurement", output_dir=data_dir, overwrite=True)
    save_omop_table(sample_drug_exposures, "drug_exposure", output_dir=data_dir, overwrite=True)

    con = duckdb.connect(":memory:")
    register_omop_tables(con, data_dir)
    yield con
    con.close()


def test_get_persons_all(test_db_with_data):
    """Test getting all persons."""
    result = get_persons(con=test_db_with_data)

    assert len(result) == 5
    assert "person_id" in result.columns


def test_get_persons_by_gender(test_db_with_data):
    """Test filtering persons by gender."""
    result = get_persons(con=test_db_with_data, gender_concept_id=8507)

    assert len(result) == 3
    assert all(result["gender_concept_id"] == 8507)


def test_get_persons_by_year_range(test_db_with_data):
    """Test filtering persons by year of birth range."""
    result = get_persons(
        con=test_db_with_data,
        year_of_birth_min=1980,
        year_of_birth_max=1990,
    )

    assert len(result) == 3
    assert all(result["year_of_birth"] >= 1980)
    assert all(result["year_of_birth"] <= 1990)


def test_get_persons_with_limit(test_db_with_data):
    """Test limiting number of persons returned."""
    result = get_persons(con=test_db_with_data, limit=2)

    assert len(result) == 2


def test_get_conditions_for_person(test_db_with_data):
    """Test getting conditions for a specific person."""
    result = get_conditions_for_person(1, con=test_db_with_data)

    assert len(result) == 2
    assert all(result["person_id"] == 1)


def test_get_conditions_with_concept_filter(test_db_with_data):
    """Test filtering conditions by concept."""
    result = get_conditions_for_person(
        1,
        con=test_db_with_data,
        condition_concept_id=320128,
    )

    assert len(result) == 1
    assert result["condition_concept_id"][0] == 320128


def test_get_conditions_with_date_filter(test_db_with_data):
    """Test filtering conditions by date range."""
    result = get_conditions_for_person(
        1,
        con=test_db_with_data,
        start_date=date(2020, 1, 1),
        end_date=date(2020, 12, 31),
    )

    assert len(result) == 2


def test_get_observations_for_person(test_db_with_data):
    """Test getting observations for a specific person."""
    result = get_observations_for_person(2, con=test_db_with_data)

    assert len(result) == 2
    assert all(result["person_id"] == 2)


def test_get_observations_with_filters(test_db_with_data):
    """Test filtering observations."""
    result = get_observations_for_person(
        2,
        con=test_db_with_data,
        observation_concept_id=4013886,
        start_date=date(2020, 2, 1),
    )

    assert len(result) == 1


def test_get_visits_for_person(test_db_with_data):
    """Test getting visits for a specific person."""
    result = get_visits_for_person(1, con=test_db_with_data)

    assert len(result) == 2
    assert all(result["person_id"] == 1)


def test_get_visits_with_concept_filter(test_db_with_data):
    """Test filtering visits by concept."""
    result = get_visits_for_person(
        1,
        con=test_db_with_data,
        visit_concept_id=9201,
    )

    assert len(result) == 2


def test_get_measurement_values(test_db_with_data):
    """Test getting measurement values for a person."""
    result = get_measurement_values(
        1,
        3004249,
        con=test_db_with_data,
    )

    assert len(result) == 3
    assert all(result["person_id"] == 1)
    assert all(result["measurement_concept_id"] == 3004249)


def test_get_measurement_values_with_date_filter(test_db_with_data):
    """Test filtering measurements by date range."""
    result = get_measurement_values(
        1,
        3004249,
        con=test_db_with_data,
        start_date=date(2020, 2, 1),
        end_date=date(2020, 12, 31),
    )

    assert len(result) == 2


def test_get_cohort_with_condition(test_db_with_data):
    """Test selecting cohort by condition."""
    result = get_cohort(
        con=test_db_with_data,
        has_condition_concept_id=320128,
    )

    assert len(result) >= 1
    person_ids = result["person_id"].to_list()
    assert 1 in person_ids


def test_get_cohort_with_drug(test_db_with_data):
    """Test selecting cohort by drug exposure."""
    result = get_cohort(
        con=test_db_with_data,
        has_drug_concept_id=1545958,
    )

    assert len(result) >= 1


def test_get_cohort_with_age_range(test_db_with_data):
    """Test selecting cohort by age range."""
    result = get_cohort(
        con=test_db_with_data,
        min_age=30,
        max_age=50,
    )

    assert len(result) >= 1
    current_year = 2026
    for row in result.iter_rows(named=True):
        age = current_year - row["year_of_birth"]
        assert 30 <= age <= 50


def test_get_cohort_with_gender(test_db_with_data):
    """Test selecting cohort by gender."""
    result = get_cohort(
        con=test_db_with_data,
        gender_concept_id=8507,
    )

    assert len(result) >= 1
    assert all(result["gender_concept_id"] == 8507)


def test_get_cohort_multiple_criteria(test_db_with_data):
    """Test selecting cohort with multiple criteria."""
    result = get_cohort(
        con=test_db_with_data,
        has_condition_concept_id=320128,
        gender_concept_id=8507,
    )

    assert len(result) >= 1
