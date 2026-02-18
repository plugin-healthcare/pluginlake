"""High-level query API for OMOP data.

Provides ergonomic Python functions for common OMOP analytical queries.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import polars as pl

from pluginlake.omop.config import get_omop_settings
from pluginlake.omop.storage import (
    get_duckdb_connection,
    query_duckdb,
    register_omop_tables,
)
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


@contextmanager
def _ensure_connection(
    con: duckdb.DuckDBPyConnection | None,
    data_dir: Path | None = None,
) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Ensure a DuckDB connection exists, creating one if needed.

    Args:
        con: Existing connection or None.
        data_dir: Data directory path or None to use config default.

    Yields:
        DuckDB connection that will be closed if created here.
    """
    should_close = con is None
    if con is None:
        settings = get_omop_settings()
        con = get_duckdb_connection()
        register_omop_tables(con, data_dir=data_dir or settings.storage_dir)

    try:
        yield con
    finally:
        if should_close:
            con.close()


def _build_filter_query(
    table: str,
    conditions: list[str],
    params: list,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build a parameterized SELECT query with WHERE clause.

    Args:
        table: Table name to query.
        conditions: List of WHERE conditions with ? placeholders.
        params: List of parameter values matching conditions.
        order_by: Optional ORDER BY clause (without ORDER BY keyword).
        limit: Optional LIMIT value.

    Returns:
        Tuple of (query_string, params_list).
    """
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = "SELECT * FROM " + table + " WHERE " + where_clause

    if order_by:
        query += " ORDER BY " + order_by
    if limit:
        query += " LIMIT " + str(limit)

    return query, params


def _execute_query(
    con: duckdb.DuckDBPyConnection,
    query: str,
    params: list,
    log_fn: Callable[[], None],
) -> pl.DataFrame:
    """Execute a parameterized query with logging.

    Args:
        con: DuckDB connection.
        query: SQL query string with ? placeholders.
        params: Parameter values.
        log_fn: Function to call for logging before execution.

    Returns:
        Query results as Polars DataFrame.
    """
    log_fn()
    return query_duckdb(con, query, params or None)


def _add_filter(
    conditions: list[str],
    params: list,
    column: str,
    operator: str,
    value: int | date | str | None,
) -> None:
    """Add a filter condition if value is not None.

    Args:
        conditions: List to append WHERE condition to.
        params: List to append parameter value to.
        column: Column name to filter on.
        operator: SQL operator (=, >=, <=, etc.).
        value: Filter value. Does nothing if None.
    """
    if value is not None:
        conditions.append(column + " " + operator + " ?")
        params.append(value)


def get_persons(
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    data_dir: Path | None = None,
    gender_concept_id: int | None = None,
    year_of_birth_min: int | None = None,
    year_of_birth_max: int | None = None,
    race_concept_id: int | None = None,
    ethnicity_concept_id: int | None = None,
    limit: int | None = None,
) -> pl.DataFrame:
    """Query persons with optional demographic filters.

    Args:
        con: DuckDB connection. Creates new connection if None.
        data_dir: Data directory path or None to use config default.
        gender_concept_id: Filter by gender concept (e.g., 8507 for male).
        year_of_birth_min: Minimum birth year (inclusive).
        year_of_birth_max: Maximum birth year (inclusive).
        race_concept_id: Filter by race concept.
        ethnicity_concept_id: Filter by ethnicity concept.
        limit: Maximum number of results.

    Returns:
        Polars DataFrame with person records.
    """
    conditions = []
    params = []

    _add_filter(conditions, params, "gender_concept_id", "=", gender_concept_id)
    _add_filter(conditions, params, "year_of_birth", ">=", year_of_birth_min)
    _add_filter(conditions, params, "year_of_birth", "<=", year_of_birth_max)
    _add_filter(conditions, params, "race_concept_id", "=", race_concept_id)
    _add_filter(conditions, params, "ethnicity_concept_id", "=", ethnicity_concept_id)

    query, params = _build_filter_query("person", conditions, params, limit=limit)

    with _ensure_connection(con, data_dir) as conn:
        return _execute_query(
            conn,
            query,
            params,
            lambda: logger.info("Querying persons", extra={"filter_count": len(conditions)}),
        )


def get_conditions_for_person(
    person_id: int,
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    data_dir: Path | None = None,
    condition_concept_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """Query conditions for a specific person.

    Args:
        person_id: Person identifier.
        con: DuckDB connection. Creates new connection if None.
        data_dir: Data directory path or None to use config default.
        condition_concept_id: Filter by specific condition concept.
        start_date: Minimum condition start date.
        end_date: Maximum condition start date.

    Returns:
        Polars DataFrame with condition occurrence records.
    """
    conditions = []
    params = []

    _add_filter(conditions, params, "person_id", "=", person_id)
    _add_filter(conditions, params, "condition_concept_id", "=", condition_concept_id)
    _add_filter(conditions, params, "condition_start_date", ">=", start_date)
    _add_filter(conditions, params, "condition_start_date", "<=", end_date)

    query, params = _build_filter_query("condition_occurrence", conditions, params)

    with _ensure_connection(con, data_dir) as conn:
        return _execute_query(
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
    data_dir: Path | None = None,
    observation_concept_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """Query observations for a specific person.

    Args:
        person_id: Person identifier.
        con: DuckDB connection. Creates new connection if None.
        data_dir: Data directory path or None to use config default.
        observation_concept_id: Filter by specific observation concept.
        start_date: Minimum observation date.
        end_date: Maximum observation date.

    Returns:
        Polars DataFrame with observation records.
    """
    conditions = []
    params = []

    _add_filter(conditions, params, "person_id", "=", person_id)
    _add_filter(conditions, params, "observation_concept_id", "=", observation_concept_id)
    _add_filter(conditions, params, "observation_date", ">=", start_date)
    _add_filter(conditions, params, "observation_date", "<=", end_date)

    query, params = _build_filter_query("observation", conditions, params)

    with _ensure_connection(con, data_dir) as conn:
        return _execute_query(
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
    data_dir: Path | None = None,
    visit_concept_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """Query visits for a specific person.

    Args:
        person_id: Person identifier.
        con: DuckDB connection. Creates new connection if None.
        data_dir: Data directory path or None to use config default.
        visit_concept_id: Filter by specific visit concept.
        start_date: Minimum visit start date.
        end_date: Maximum visit start date.

    Returns:
        Polars DataFrame with visit occurrence records.
    """
    conditions = []
    params = []

    _add_filter(conditions, params, "person_id", "=", person_id)
    _add_filter(conditions, params, "visit_concept_id", "=", visit_concept_id)
    _add_filter(conditions, params, "visit_start_date", ">=", start_date)
    _add_filter(conditions, params, "visit_start_date", "<=", end_date)

    query, params = _build_filter_query("visit_occurrence", conditions, params)

    with _ensure_connection(con, data_dir) as conn:
        return _execute_query(
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
    data_dir: Path | None = None,
    has_condition_concept_id: int | None = None,
    has_drug_concept_id: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
    gender_concept_id: int | None = None,
) -> pl.DataFrame:
    """Select cohort of persons matching clinical criteria.

    Args:
        con: DuckDB connection. Creates new connection if None.
        data_dir: Data directory path or None to use config default.
        has_condition_concept_id: Persons with this condition.
        has_drug_concept_id: Persons exposed to this drug.
        min_age: Minimum age in years (calculated from current year).
        max_age: Maximum age in years.
        gender_concept_id: Gender filter.

    Returns:
        Polars DataFrame with person_id and matching criteria.
    """
    from_clause = "person p"
    where_clauses = []
    params = []

    if has_condition_concept_id is not None:
        from_clause += """
            INNER JOIN condition_occurrence co
                ON p.person_id = co.person_id
        """
        _add_filter(where_clauses, params, "co.condition_concept_id", "=", has_condition_concept_id)

    if has_drug_concept_id is not None:
        from_clause += """
            INNER JOIN drug_exposure de
                ON p.person_id = de.person_id
        """
        _add_filter(where_clauses, params, "de.drug_concept_id", "=", has_drug_concept_id)

    current_year = datetime.now(UTC).date().year
    if min_age is not None:
        max_birth_year = current_year - min_age
        _add_filter(where_clauses, params, "p.year_of_birth", "<=", max_birth_year)

    if max_age is not None:
        min_birth_year = current_year - max_age
        _add_filter(where_clauses, params, "p.year_of_birth", ">=", min_birth_year)

    _add_filter(where_clauses, params, "p.gender_concept_id", "=", gender_concept_id)

    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
    query = "SELECT DISTINCT p.* FROM " + from_clause + " WHERE " + where_clause

    with _ensure_connection(con, data_dir) as conn:
        return _execute_query(
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
    data_dir: Path | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """Query measurement values for a person and measurement type.

    Args:
        person_id: Person identifier.
        measurement_concept_id: Measurement concept (e.g., lab test).
        con: DuckDB connection. Creates new connection if None.
        data_dir: Data directory path or None to use config default.
        start_date: Minimum measurement date.
        end_date: Maximum measurement date.

    Returns:
        Polars DataFrame with measurement records.
    """
    conditions = []
    params = []

    _add_filter(conditions, params, "person_id", "=", person_id)
    _add_filter(conditions, params, "measurement_concept_id", "=", measurement_concept_id)
    _add_filter(conditions, params, "measurement_date", ">=", start_date)
    _add_filter(conditions, params, "measurement_date", "<=", end_date)

    query, params = _build_filter_query("measurement", conditions, params, order_by="measurement_date")

    with _ensure_connection(con, data_dir) as conn:
        return _execute_query(
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
