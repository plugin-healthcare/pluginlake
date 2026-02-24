"""Query API for OMOP vocabularies.

Functions for querying OMOP controlled vocabularies.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import duckdb
import polars as pl

from pluginlake.omop.config import get_omop_settings
from pluginlake.omop.loader import load_vocabulary_dataset
from pluginlake.omop.storage import (
    get_duckdb_connection,
    query_duckdb,
    register_vocabulary_tables,
    save_vocabulary_table,
)
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


@contextmanager
def _ensure_vocabulary_connection(
    con: duckdb.DuckDBPyConnection | None,
    data_dir: Path | None = None,
) -> Generator[duckdb.DuckDBPyConnection]:
    """Ensure DuckDB connection with vocabularies loaded.

    Args:
        con: Existing connection or None.
        data_dir: Vocabulary data directory or None to use config default.

    Yields:
        DuckDB connection with vocabulary tables registered.
    """
    should_close = con is None
    settings = get_omop_settings()

    if con is None:
        con = get_duckdb_connection()

    vocabulary_dir = data_dir or settings.vocabulary_dir
    parquet_dir = vocabulary_dir / "parquet"

    if not parquet_dir.exists() or not list(parquet_dir.glob("*.parquet")):
        if settings.vocabulary_auto_load:
            logger.info("Vocabularies not found in Parquet format, loading from source files")
            try:
                vocab_tables = load_vocabulary_dataset(vocabulary_dir)
                if vocab_tables:
                    for table_name, df in vocab_tables.items():
                        save_vocabulary_table(df, table_name, output_dir=parquet_dir, overwrite=True)
            except Exception:
                logger.exception("Failed to auto-load vocabularies")
                if should_close:
                    con.close()
                raise

    register_vocabulary_tables(con, data_dir=parquet_dir)

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
    """Execute vocabulary query with logging.

    Args:
        con: DuckDB connection.
        query: SQL query with $param placeholders.
        params: Parameter dictionary.
        log_fn: Logging function to call before execution.

    Returns:
        Query results as Polars DataFrame.
    """
    log_fn()
    return query_duckdb(con, query, params)


def get_concept(
    concept_id: int,
    con: duckdb.DuckDBPyConnection | None = None,
    data_dir: Path | None = None,
    *,
    schema: str = "omop_vocab",
) -> pl.DataFrame:
    """Get concept details by ID.

    Args:
        concept_id: Concept ID to retrieve.
        con: DuckDB connection or None to create one.
        data_dir: Vocabulary directory or None for config default.
        schema: DuckDB schema name for vocabulary tables.

    Returns:
        DataFrame with concept details (single row if found, empty if not).
    """
    with _ensure_vocabulary_connection(con, data_dir) as conn:
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
    data_dir: Path | None = None,
    schema: str = "omop_vocab",
) -> pl.DataFrame:
    """Search concepts by name.

    Args:
        term: Search term (case-insensitive).
        domain_id: Filter by domain (e.g., 'Condition', 'Drug').
        vocabulary_id: Filter by vocabulary (e.g., 'SNOMED', 'RxNorm').
        standard_only: Only return standard concepts.
        limit: Maximum results to return.
        con: DuckDB connection or None to create one.
        data_dir: Vocabulary directory or None for config default.
        schema: DuckDB schema name for vocabulary tables.

    Returns:
        DataFrame with matching concepts.
    """
    with _ensure_vocabulary_connection(con, data_dir) as conn:
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
    data_dir: Path | None = None,
    schema: str = "omop_vocab",
) -> pl.DataFrame:
    """Get all descendant concepts in hierarchy.

    Args:
        ancestor_concept_id: Ancestor concept ID.
        max_levels: Maximum hierarchy levels to traverse (None for all).
        con: DuckDB connection or None to create one.
        data_dir: Vocabulary directory or None for config default.
        schema: DuckDB schema name for vocabulary tables.

    Returns:
        DataFrame with descendant concepts and separation levels.
    """
    with _ensure_vocabulary_connection(con, data_dir) as conn:
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
    data_dir: Path | None = None,
    schema: str = "omop_vocab",
) -> pl.DataFrame:
    """Get all ancestor concepts in hierarchy.

    Args:
        descendant_concept_id: Descendant concept ID.
        max_levels: Maximum hierarchy levels to traverse (None for all).
        con: DuckDB connection or None to create one.
        data_dir: Vocabulary directory or None for config default.
        schema: DuckDB schema name for vocabulary tables.

    Returns:
        DataFrame with ancestor concepts and separation levels.
    """
    with _ensure_vocabulary_connection(con, data_dir) as conn:
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
    data_dir: Path | None = None,
    schema: str = "omop_vocab",
) -> pl.DataFrame:
    """Map source code to standard concept.

    Args:
        source_code: Source code to map.
        source_vocabulary_id: Source vocabulary (e.g., 'ICD10CM', 'ICD9CM').
        con: DuckDB connection or None to create one.
        data_dir: Vocabulary directory or None for config default.
        schema: DuckDB schema name for vocabulary tables.

    Returns:
        DataFrame with mapping and target concept details.
    """
    with _ensure_vocabulary_connection(con, data_dir) as conn:
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
    data_dir: Path | None = None,
    schema: str = "omop_vocab",
) -> pl.DataFrame:
    """Get vocabulary metadata.

    Args:
        vocabulary_id: Specific vocabulary ID or None for all.
        con: DuckDB connection or None to create one.
        data_dir: Vocabulary directory or None for config default.
        schema: DuckDB schema name for vocabulary tables.

    Returns:
        DataFrame with vocabulary information.
    """
    with _ensure_vocabulary_connection(con, data_dir) as conn:
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
