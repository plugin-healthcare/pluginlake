"""Query API for OMOP vocabularies.

Functions for querying OMOP controlled vocabularies.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager

import duckdb
import polars as pl

from pluginlake.core.ducklake.setup import setup_ducklake
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


@contextmanager
def _ensure_connection(
    con: duckdb.DuckDBPyConnection | None,
) -> Generator[duckdb.DuckDBPyConnection]:
    should_close = con is None
    if con is None:
        con = setup_ducklake()
    try:
        yield con
    finally:
        if should_close:
            con.close()


def _execute_query(
    con: duckdb.DuckDBPyConnection,
    query: str,
    params: dict | None,
    log_fn: Callable[[], None],
) -> pl.DataFrame:
    log_fn()
    result = con.execute(query, params) if params else con.execute(query)
    columns = [desc[0] for desc in result.description]
    return pl.DataFrame(result.fetchall(), schema=columns, orient="row")


def get_concept(
    concept_id: int,
    con: duckdb.DuckDBPyConnection | None = None,
    *,
    schema: str = "ducklake.omop_vocab",
) -> pl.DataFrame:
    """Retrieve a single concept by ID."""
    with _ensure_connection(con) as conn:
        query = f"""
            SELECT
                concept_id,
                concept_name,
                domain_id,
                vocabulary_id,
                concept_class_id,
                standard_concept,
                concept_code,
                valid_start_date,
                valid_end_date,
                invalid_reason
            FROM {schema}.concept
            WHERE concept_id = $concept_id
        """  # noqa: S608

        return _execute_query(
            conn,
            query,
            {"concept_id": concept_id},
            lambda: logger.debug("Retrieving concept: %d", concept_id),
        )


def search_concepts(  # noqa: PLR0913
    term: str,
    domain_id: str | None = None,
    vocabulary_id: str | None = None,
    *,
    standard_only: bool = True,
    limit: int = 100,
    con: duckdb.DuckDBPyConnection | None = None,
    schema: str = "ducklake.omop_vocab",
) -> pl.DataFrame:
    """Search concepts by name with optional domain, vocabulary, and standard filters."""
    with _ensure_connection(con) as conn:
        conditions = []
        params = {"term": f"%{term}%", "limit": limit}

        conditions.append("LOWER(concept_name) LIKE LOWER($term)")

        if domain_id:
            conditions.append("domain_id = $domain_id")
            params["domain_id"] = domain_id

        if vocabulary_id:
            conditions.append("vocabulary_id = $vocabulary_id")
            params["vocabulary_id"] = vocabulary_id

        if standard_only:
            conditions.append("standard_concept = 'S'")

        conditions.append("invalid_reason IS NULL")

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                concept_id,
                concept_name,
                domain_id,
                vocabulary_id,
                concept_class_id,
                standard_concept,
                concept_code
            FROM {schema}.concept
            WHERE {where_clause}
            ORDER BY concept_name
            LIMIT $limit
        """  # noqa: S608

        return _execute_query(
            conn,
            query,
            params,
            lambda: logger.debug("Searching concepts: '%s'", term),
        )


def get_concept_descendants(
    ancestor_concept_id: int,
    max_levels: int | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    schema: str = "ducklake.omop_vocab",
) -> pl.DataFrame:
    """Return all descendant concepts of an ancestor concept."""
    with _ensure_connection(con) as conn:
        params = {"ancestor_id": ancestor_concept_id}
        max_levels_clause = ""

        if max_levels is not None:
            max_levels_clause = "AND ca.max_levels_of_separation <= $max_levels"
            params["max_levels"] = max_levels

        query = f"""
            SELECT
                c.concept_id,
                c.concept_name,
                c.domain_id,
                c.vocabulary_id,
                c.concept_class_id,
                c.standard_concept,
                ca.min_levels_of_separation,
                ca.max_levels_of_separation
            FROM {schema}.concept_ancestor ca
            JOIN {schema}.concept c ON ca.descendant_concept_id = c.concept_id
            WHERE ca.ancestor_concept_id = $ancestor_id
              {max_levels_clause}
            ORDER BY ca.min_levels_of_separation, c.concept_name
        """  # noqa: S608

        return _execute_query(
            conn,
            query,
            params,
            lambda: logger.debug("Getting descendants of concept: %d", ancestor_concept_id),
        )


def get_concept_ancestors(
    descendant_concept_id: int,
    max_levels: int | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    schema: str = "ducklake.omop_vocab",
) -> pl.DataFrame:
    """Return all ancestor concepts of a descendant concept."""
    with _ensure_connection(con) as conn:
        params = {"descendant_id": descendant_concept_id}
        max_levels_clause = ""

        if max_levels is not None:
            max_levels_clause = "AND ca.max_levels_of_separation <= $max_levels"
            params["max_levels"] = max_levels

        query = f"""
            SELECT
                c.concept_id,
                c.concept_name,
                c.domain_id,
                c.vocabulary_id,
                c.concept_class_id,
                c.standard_concept,
                ca.min_levels_of_separation,
                ca.max_levels_of_separation
            FROM {schema}.concept_ancestor ca
            JOIN {schema}.concept c ON ca.ancestor_concept_id = c.concept_id
            WHERE ca.descendant_concept_id = $descendant_id
              {max_levels_clause}
            ORDER BY ca.min_levels_of_separation, c.concept_name
        """  # noqa: S608

        return _execute_query(
            conn,
            query,
            params,
            lambda: logger.debug("Getting ancestors of concept: %d", descendant_concept_id),
        )


def map_source_code(
    source_code: str,
    source_vocabulary_id: str,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    schema: str = "ducklake.omop_vocab",
) -> pl.DataFrame:
    """Map a source code to its standard OMOP concept via the source-to-concept map."""
    with _ensure_connection(con) as conn:
        query = f"""
            SELECT
                stcm.source_code,
                stcm.source_concept_id,
                stcm.source_vocabulary_id,
                stcm.source_code_description,
                stcm.target_concept_id,
                c.concept_name as target_concept_name,
                c.domain_id as target_domain_id,
                c.vocabulary_id as target_vocabulary_id,
                c.concept_class_id as target_concept_class_id,
                c.standard_concept as target_standard_concept
            FROM {schema}.source_to_concept_map stcm
            JOIN {schema}.concept c ON stcm.target_concept_id = c.concept_id
            WHERE stcm.source_code = $source_code
              AND stcm.source_vocabulary_id = $source_vocabulary_id
              AND stcm.invalid_reason IS NULL
              AND c.invalid_reason IS NULL
            ORDER BY stcm.target_concept_id
        """  # noqa: S608

        return _execute_query(
            conn,
            query,
            {"source_code": source_code, "source_vocabulary_id": source_vocabulary_id},
            lambda: logger.debug("Mapping source code: %s (%s)", source_code, source_vocabulary_id),
        )


def get_vocabulary_info(
    vocabulary_id: str | None = None,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    schema: str = "ducklake.omop_vocab",
) -> pl.DataFrame:
    """Return vocabulary metadata, optionally filtered by vocabulary ID."""
    with _ensure_connection(con) as conn:
        where_clause = ""
        params = {}

        if vocabulary_id:
            where_clause = "WHERE vocabulary_id = $vocabulary_id"
            params["vocabulary_id"] = vocabulary_id

        query = f"""
            SELECT
                vocabulary_id,
                vocabulary_name,
                vocabulary_reference,
                vocabulary_version,
                vocabulary_concept_id
            FROM {schema}.vocabulary
            {where_clause}
            ORDER BY vocabulary_id
        """  # noqa: S608

        return _execute_query(
            conn,
            query,
            params or None,
            lambda: logger.debug("Getting vocabulary info"),
        )
