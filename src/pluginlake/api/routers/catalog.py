"""DuckLake catalog endpoints.

- ``GET /api/v1/catalog/schemas``  — list schemas
- ``GET /api/v1/catalog/tables``   — list tables (optionally filtered by schema)
- ``GET /api/v1/catalog/columns``  — list columns for a specific table
"""

import re
from collections import defaultdict
from typing import Annotated, Any

import duckdb
from fastapi import APIRouter, HTTPException, Query

from pluginlake.core.ducklake.setup import shared_cursor
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_identifier(name: str, label: str) -> str:
    """Validate a SQL identifier to prevent injection.

    Args:
        name: The identifier value to validate.
        label: Human-readable label for error messages (e.g. 'schema').

    Returns:
        The validated identifier.

    Raises:
        HTTPException: If the identifier contains invalid characters.
    """
    if not _IDENTIFIER_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid {label}: {name!r}")
    return name


def _query_ducklake(sql: str, params: list[Any] | dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute a SQL query against DuckLake and return rows as dicts."""
    cursor = shared_cursor()
    try:
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description or []]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        cursor.close()


@router.get(
    "/schemas",
    summary="List DuckLake schemas",
    description="Returns all schemas in the DuckLake catalog.",
)
def list_schemas() -> list[dict[str, Any]]:
    """List all schemas in the DuckLake catalog."""
    try:
        return _query_ducklake(
            "SELECT DISTINCT table_schema AS schema_name "
            "FROM information_schema.tables "
            "WHERE table_catalog = 'ducklake' "
            "ORDER BY table_schema"
        )
    except Exception:
        logger.exception("Failed to list DuckLake schemas")
        return []


@router.get(
    "/tables",
    summary="List DuckLake tables",
    description="Returns tables in the DuckLake catalog, optionally filtered by schema.",
)
def list_tables(
    schema: Annotated[str | None, Query(description="Filter by schema name")] = None,
) -> list[dict[str, Any]]:
    """List tables in the DuckLake catalog with column counts."""
    if schema:
        schema = _validate_identifier(schema, "schema")
    try:
        return _query_ducklake(
            "SELECT t.table_schema, t.table_name, "
            "COUNT(c.column_name) AS column_count "
            "FROM information_schema.tables t "
            "LEFT JOIN information_schema.columns c "
            "ON t.table_catalog = c.table_catalog "
            "AND t.table_schema = c.table_schema "
            "AND t.table_name = c.table_name "
            "WHERE t.table_catalog = 'ducklake' "
            "AND ($schema IS NULL OR t.table_schema = $schema) "
            "GROUP BY t.table_schema, t.table_name "
            "ORDER BY t.table_schema, t.table_name",
            {"schema": schema},
        )
    except Exception:
        logger.exception("Failed to list DuckLake tables")
        return []


@router.get(
    "/columns",
    summary="List columns for a DuckLake table",
    description="Returns column names, types, nullability, and ordinal position for a table.",
)
def list_columns(
    schema: Annotated[str, Query(description="Schema name")],
    table: Annotated[str, Query(description="Table name")],
) -> list[dict[str, Any]]:
    """List columns for a specific DuckLake table."""
    schema = _validate_identifier(schema, "schema")
    table = _validate_identifier(table, "table")
    try:
        rows = _query_ducklake(
            "SELECT column_name, data_type, is_nullable, ordinal_position, "
            "column_default "
            "FROM information_schema.columns "
            "WHERE table_catalog = 'ducklake' AND table_schema = ? AND table_name = ? "
            "ORDER BY ordinal_position",
            [schema, table],
        )
    except Exception:
        logger.exception("Failed to list columns for %s.%s", schema, table)
        return []

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{schema}.{table}' not found or has no columns.",
        )
    return rows


@router.get(
    "/column-stats",
    summary="Get column-level statistics for a DuckLake table",
    description=(
        "Returns per-column statistics including type, unique count, "
        "null percentage, min, max, and quartiles using DuckDB SUMMARIZE."
    ),
)
def column_stats(
    schema: Annotated[str, Query(description="Schema name")],
    table: Annotated[str, Query(description="Table name")],
) -> list[dict[str, Any]]:
    """Return column-level statistics using DuckDB SUMMARIZE."""
    schema = _validate_identifier(schema, "schema")
    table = _validate_identifier(table, "table")
    try:
        return _query_ducklake(f"SUMMARIZE SELECT * FROM ducklake.{schema}.{table}")
    except Exception:
        logger.exception("Failed to compute column stats for %s.%s", schema, table)
        return []


@router.get(
    "/layer-summary",
    summary="Get per-schema layer summary",
    description="Returns table count and total row count for each DuckLake schema.",
)
def layer_summary() -> list[dict[str, Any]]:
    """Return a summary of each schema (layer) in the DuckLake catalog."""
    tables = _query_ducklake(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_catalog = 'ducklake' ORDER BY table_schema, table_name"
    )

    table_counts: dict[str, int] = defaultdict(int)
    row_counts: dict[str, int] = defaultdict(int)
    for row in tables:
        schema_name, table_name = row["table_schema"], row["table_name"]
        table_counts[schema_name] += 1
        try:
            [count] = _query_ducklake(f'SELECT COUNT(*) AS n FROM ducklake."{schema_name}"."{table_name}"')
            row_counts[schema_name] += count["n"]
        except duckdb.Error:
            logger.warning("Could not count rows in %s.%s", schema_name, table_name)

    return [
        {"schema_name": schema_name, "table_count": count, "total_rows": row_counts[schema_name]}
        for schema_name, count in table_counts.items()
    ]
