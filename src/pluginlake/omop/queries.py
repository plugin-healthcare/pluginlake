"""High-level query API for OMOP data.

Provides ergonomic Python functions for common OMOP analytical queries.
"""

from datetime import UTC, date, datetime

import duckdb
import polars as pl

from pluginlake.omop.query_utils import add_filter, build_filter_query, ensure_connection, execute_query
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def get_persons(
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    gender_concept_id: int | None = None,
    year_of_birth_min: int | None = None,
    year_of_birth_max: int | None = None,
    race_concept_id: int | None = None,
    ethnicity_concept_id: int | None = None,
    limit: int | None = None,
) -> pl.DataFrame:
    """Query person records with optional filters."""
    conditions = []
    params = []

    add_filter(conditions, params, "gender_concept_id", "=", gender_concept_id)
    add_filter(conditions, params, "year_of_birth", ">=", year_of_birth_min)
    add_filter(conditions, params, "year_of_birth", "<=", year_of_birth_max)
    add_filter(conditions, params, "race_concept_id", "=", race_concept_id)
    add_filter(conditions, params, "ethnicity_concept_id", "=", ethnicity_concept_id)

    query, params = build_filter_query("ducklake.omop.person", conditions, params, limit=limit)

    with ensure_connection(con) as conn:
        return execute_query(
            conn,
            query,
            params,
            lambda: logger.info("Querying persons", extra={"filter_count": len(conditions)}),
        )


def get_conditions_for_person(
    person_id: int,
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    condition_concept_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """Query condition occurrences for a person with optional filters."""
    conditions = []
    params = []

    add_filter(conditions, params, "person_id", "=", person_id)
    add_filter(conditions, params, "condition_concept_id", "=", condition_concept_id)
    add_filter(conditions, params, "condition_start_date", ">=", start_date)
    add_filter(conditions, params, "condition_start_date", "<=", end_date)

    query, params = build_filter_query("ducklake.omop.condition_occurrence", conditions, params)

    with ensure_connection(con) as conn:
        return execute_query(
            conn,
            query,
            params,
            lambda: logger.info(
                "Querying conditions for person",
                extra={"person_id": person_id, "filter_count": len(conditions)},
            ),
        )


def get_observations_for_person(
    person_id: int,
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    observation_concept_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """Query observations for a person with optional filters."""
    conditions = []
    params = []

    add_filter(conditions, params, "person_id", "=", person_id)
    add_filter(conditions, params, "observation_concept_id", "=", observation_concept_id)
    add_filter(conditions, params, "observation_date", ">=", start_date)
    add_filter(conditions, params, "observation_date", "<=", end_date)

    query, params = build_filter_query("ducklake.omop.observation", conditions, params)

    with ensure_connection(con) as conn:
        return execute_query(
            conn,
            query,
            params,
            lambda: logger.info(
                "Querying observations for person",
                extra={"person_id": person_id, "filter_count": len(conditions)},
            ),
        )


def get_visits_for_person(
    person_id: int,
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    visit_concept_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """Query visit occurrences for a person with optional filters."""
    conditions = []
    params = []

    add_filter(conditions, params, "person_id", "=", person_id)
    add_filter(conditions, params, "visit_concept_id", "=", visit_concept_id)
    add_filter(conditions, params, "visit_start_date", ">=", start_date)
    add_filter(conditions, params, "visit_start_date", "<=", end_date)

    query, params = build_filter_query("ducklake.omop.visit_occurrence", conditions, params)

    with ensure_connection(con) as conn:
        return execute_query(
            conn,
            query,
            params,
            lambda: logger.info(
                "Querying visits for person",
                extra={"person_id": person_id, "filter_count": len(conditions)},
            ),
        )


def get_cohort(
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    has_condition_concept_id: int | None = None,
    has_drug_concept_id: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
    gender_concept_id: int | None = None,
) -> pl.DataFrame:
    """Select a cohort of persons matching the given clinical criteria."""
    from_clause = "ducklake.omop.person p"
    where_clauses = []
    params = []

    if has_condition_concept_id is not None:
        from_clause += """
            INNER JOIN ducklake.omop.condition_occurrence co
                ON p.person_id = co.person_id
        """
        add_filter(where_clauses, params, "co.condition_concept_id", "=", has_condition_concept_id)

    if has_drug_concept_id is not None:
        from_clause += """
            INNER JOIN ducklake.omop.drug_exposure de
                ON p.person_id = de.person_id
        """
        add_filter(where_clauses, params, "de.drug_concept_id", "=", has_drug_concept_id)

    current_year = datetime.now(UTC).date().year
    if min_age is not None:
        max_birth_year = current_year - min_age
        add_filter(where_clauses, params, "p.year_of_birth", "<=", max_birth_year)

    if max_age is not None:
        min_birth_year = current_year - max_age
        add_filter(where_clauses, params, "p.year_of_birth", ">=", min_birth_year)

    add_filter(where_clauses, params, "p.gender_concept_id", "=", gender_concept_id)

    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
    query = "SELECT DISTINCT p.* FROM " + from_clause + " WHERE " + where_clause

    with ensure_connection(con) as conn:
        return execute_query(
            conn,
            query,
            params,
            lambda: logger.info(
                "Selecting cohort",
                extra={
                    "criteria_count": len(where_clauses),
                    "has_condition": has_condition_concept_id is not None,
                    "has_drug": has_drug_concept_id is not None,
                },
            ),
        )


def get_measurement_values(
    person_id: int,
    measurement_concept_id: int,
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """Query measurement values for a person and concept with optional date filters."""
    conditions = []
    params = []

    add_filter(conditions, params, "person_id", "=", person_id)
    add_filter(conditions, params, "measurement_concept_id", "=", measurement_concept_id)
    add_filter(conditions, params, "measurement_date", ">=", start_date)
    add_filter(conditions, params, "measurement_date", "<=", end_date)

    query, params = build_filter_query("ducklake.omop.measurement", conditions, params, order_by="measurement_date")

    with ensure_connection(con) as conn:
        return execute_query(
            conn,
            query,
            params,
            lambda: logger.info(
                "Querying measurement values",
                extra={
                    "person_id": person_id,
                    "measurement_concept_id": measurement_concept_id,
                },
            ),
        )
