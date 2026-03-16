"""OMOP vocabulary validation functions.

Functions for validating clinical data against OMOP controlled vocabularies.
"""

import duckdb
import polars as pl

from pluginlake.omop.schemas import get_omop_schema
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def validate_concept_ids(  # noqa: PLR0913
    conn: duckdb.DuckDBPyConnection,
    concept_ids: list[int],
    domain_id: str | None = None,
    vocabulary_id: str | None = None,
    *,
    standard_only: bool = True,
    schema: str = "ducklake.omop_vocab",
) -> pl.DataFrame:
    """Validate concept IDs against vocabulary tables.

    Args:
        conn: DuckDB connection with registered vocabulary tables.
        concept_ids: List of concept IDs to validate.
        domain_id: Optional domain filter (e.g., 'Condition', 'Drug').
        vocabulary_id: Optional vocabulary filter (e.g., 'SNOMED', 'RxNorm').
        standard_only: If True, only accept standard concepts (standard_concept='S').
        schema: DuckDB schema name for vocabulary tables.

    Returns:
        DataFrame with columns: concept_id, concept_name, is_valid, validation_message,
        domain_id, vocabulary_id, standard_concept.
    """
    if not concept_ids:
        return pl.DataFrame(
            schema={
                "concept_id": pl.Int64,
                "concept_name": pl.Utf8,
                "is_valid": pl.Boolean,
                "validation_message": pl.Utf8,
                "domain_id": pl.Utf8,
                "vocabulary_id": pl.Utf8,
                "standard_concept": pl.Utf8,
            }
        )

    query = f"""
    WITH input_concepts AS (
        SELECT UNNEST($concept_ids::INTEGER[]) as concept_id
    )
    SELECT
        ic.concept_id,
        c.concept_name,
        c.domain_id,
        c.vocabulary_id,
        c.standard_concept,
        CASE
            WHEN c.concept_id IS NULL THEN false
            WHEN c.invalid_reason IS NOT NULL THEN false
            WHEN $standard_only AND (c.standard_concept IS NULL OR c.standard_concept != 'S') THEN false
            WHEN $domain_id IS NOT NULL AND c.domain_id != $domain_id THEN false
            WHEN $vocabulary_id IS NOT NULL AND c.vocabulary_id != $vocabulary_id THEN false
            ELSE true
        END as is_valid,
        CASE
            WHEN c.concept_id IS NULL THEN 'Concept ID does not exist'
            WHEN c.invalid_reason = 'D' THEN 'Concept is deleted'
            WHEN c.invalid_reason = 'U' THEN 'Concept is updated/deprecated'
            WHEN c.invalid_reason IS NOT NULL THEN 'Concept is invalid: ' || c.invalid_reason
            WHEN $standard_only AND (c.standard_concept IS NULL OR c.standard_concept != 'S') THEN 'Not a standard concept'
            WHEN $domain_id IS NOT NULL AND c.domain_id != $domain_id THEN 'Wrong domain (expected ' || $domain_id || ', got ' || c.domain_id || ')'
            WHEN $vocabulary_id IS NOT NULL AND c.vocabulary_id != $vocabulary_id THEN 'Wrong vocabulary (expected ' || $vocabulary_id || ', got ' || c.vocabulary_id || ')'
            ELSE 'Valid'
        END as validation_message
    FROM input_concepts ic
    LEFT JOIN {schema}.concept c ON ic.concept_id = c.concept_id
    ORDER BY ic.concept_id
    """  # noqa: S608

    params = {
        "concept_ids": concept_ids,
        "standard_only": standard_only,
        "domain_id": domain_id,
        "vocabulary_id": vocabulary_id,
    }
    cursor = conn.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    result = pl.DataFrame(cursor.fetchall(), schema=columns, orient="row")

    invalid_count = result.filter(~pl.col("is_valid")).height
    if invalid_count > 0:
        logger.warning(
            "Found %d invalid concept IDs out of %d total",
            invalid_count,
            len(concept_ids),
            extra={"invalid_count": invalid_count, "total_count": len(concept_ids)},
        )

    return result


def validate_table_concepts(
    conn: duckdb.DuckDBPyConnection,
    df: pl.DataFrame,
    table_name: str,
    *,
    schema: str = "ducklake.omop_vocab",
) -> pl.DataFrame:
    """Validate all concept_id columns in a clinical data table.

    Args:
        conn: DuckDB connection with registered vocabulary tables.
        df: Clinical data DataFrame to validate.
        table_name: OMOP table name to get schema.
        schema: DuckDB schema name for vocabulary tables.

    Returns:
        DataFrame with validation results for each concept column.
        Columns: column_name, concept_id, is_valid, validation_message.
    """
    omop_schema = get_omop_schema(table_name)
    if not omop_schema:
        logger.warning("No schema definition for table: %s", table_name)
        return pl.DataFrame(
            schema={
                "column_name": pl.Utf8,
                "concept_id": pl.Int64,
                "is_valid": pl.Boolean,
                "validation_message": pl.Utf8,
            }
        )

    concept_columns = [
        col_name
        for col_name, field in omop_schema.model_fields.items()
        if col_name.endswith("_concept_id") and col_name in df.columns
    ]

    if not concept_columns:
        logger.info("No concept_id columns found in table: %s", table_name)
        return pl.DataFrame(
            schema={
                "column_name": pl.Utf8,
                "concept_id": pl.Int64,
                "is_valid": pl.Boolean,
                "validation_message": pl.Utf8,
            }
        )

    all_results = []
    for col_name in concept_columns:
        concept_ids = df[col_name].drop_nulls().unique().to_list()
        if not concept_ids:
            continue

        validation_result = validate_concept_ids(conn, concept_ids, standard_only=False, schema=schema)

        validation_result = validation_result.with_columns(pl.lit(col_name).alias("column_name")).select(
            ["column_name", "concept_id", "is_valid", "validation_message"]
        )

        all_results.append(validation_result)

    if not all_results:
        return pl.DataFrame(
            schema={
                "column_name": pl.Utf8,
                "concept_id": pl.Int64,
                "is_valid": pl.Boolean,
                "validation_message": pl.Utf8,
            }
        )

    combined = pl.concat(all_results)

    invalid_by_column = (
        combined.filter(~pl.col("is_valid")).group_by("column_name").agg(pl.len().alias("invalid_count"))
    )

    for row in invalid_by_column.iter_rows(named=True):
        logger.warning(
            "Column %s has %d invalid concepts in table %s",
            row["column_name"],
            row["invalid_count"],
            table_name,
            extra={
                "table_name": table_name,
                "column_name": row["column_name"],
                "invalid_count": row["invalid_count"],
            },
        )

    return combined


def filter_invalid_rows(
    df: pl.DataFrame,
    validation_result: pl.DataFrame,
    table_name: str,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Split a DataFrame into valid and invalid rows based on vocabulary validation.

    A row is considered invalid if ANY of its concept_id columns contains a
    concept ID that failed validation. Null concept_id values are treated as valid.

    Args:
        df: Source clinical data DataFrame.
        validation_result: Output of ``validate_table_concepts`` with
            columns ``column_name``, ``concept_id``, ``is_valid``.
        table_name: OMOP table name (for logging).

    Returns:
        Tuple of ``(valid_df, invalid_df)`` where ``valid_df`` contains only
        rows with all-valid concept IDs and ``invalid_df`` contains the rest.
    """
    if validation_result.height == 0:
        return df, df.clear()

    invalid = validation_result.filter(~pl.col("is_valid"))
    if invalid.height == 0:
        return df, df.clear()

    invalid_ids_by_column: dict[str, set[int]] = {}
    for row in invalid.iter_rows(named=True):
        col = row["column_name"]
        if col not in invalid_ids_by_column:
            invalid_ids_by_column[col] = set()
        invalid_ids_by_column[col].add(row["concept_id"])

    is_invalid = pl.lit(value=False)
    for col_name, bad_ids in invalid_ids_by_column.items():
        if col_name not in df.columns:
            continue
        is_invalid = is_invalid | (pl.col(col_name).is_in(list(bad_ids)) & pl.col(col_name).is_not_null())

    valid_df = df.filter(~is_invalid)
    invalid_df = df.filter(is_invalid)

    logger.info(
        "Filtered %s: %d valid, %d invalid out of %d total rows",
        table_name,
        valid_df.height,
        invalid_df.height,
        df.height,
        extra={
            "table_name": table_name,
            "valid_count": valid_df.height,
            "invalid_count": invalid_df.height,
            "total_count": df.height,
        },
    )

    return valid_df, invalid_df


def write_audit_table(
    conn: duckdb.DuckDBPyConnection,
    validation_result: pl.DataFrame,
    table_name: str,
    *,
    schema: str = "ducklake.omop_audit",
) -> None:
    """Persist vocabulary validation results to an audit table.

    Creates or replaces ``{schema}.{table_name}`` with the validation result
    so users can query which concept IDs passed or failed validation.

    Args:
        conn: DuckDB connection with DuckLake catalog attached.
        validation_result: Output of ``validate_table_concepts``.
        table_name: OMOP table name used as the audit table name.
        schema: DuckDB schema for audit tables.
    """
    if validation_result.height == 0:
        return

    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    ref = f"{schema}.{table_name}"
    conn.register("_audit_data", validation_result)
    conn.execute(f"CREATE OR REPLACE TABLE {ref} AS SELECT * FROM _audit_data")  # noqa: S608 — schema/table from trusted config
    conn.unregister("_audit_data")

    logger.info(
        "Wrote %d audit rows to %s",
        validation_result.height,
        ref,
        extra={"table_name": table_name, "row_count": validation_result.height},
    )
