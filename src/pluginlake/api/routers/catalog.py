"""DuckLake catalog endpoints.

- ``GET /api/v1/catalog/schemas``  — list schemas
- ``GET /api/v1/catalog/tables``   — list tables (optionally filtered by schema)
- ``GET /api/v1/catalog/columns``  — list columns for a specific table
"""

import re
from typing import Annotated, Any

import duckdb
from fastapi import APIRouter, HTTPException, Query

from pluginlake.core.config import DuckLakeSettings
from pluginlake.core.ducklake.setup import create_connection
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


def _query_ducklake(sql: str) -> list[dict[str, Any]]:
    """Execute a SQL query against DuckLake and return rows as dicts."""
    settings = DuckLakeSettings()  # type: ignore[missing-argument]
    conn = create_connection(settings)
    try:
        result = conn.sql(sql)
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    finally:
        conn.close()


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
    try:
        sql = (
            "SELECT t.table_schema, t.table_name, "
            "COUNT(c.column_name) AS column_count "
            "FROM information_schema.tables t "
            "LEFT JOIN information_schema.columns c "
            "ON t.table_catalog = c.table_catalog "
            "AND t.table_schema = c.table_schema "
            "AND t.table_name = c.table_name "
            "WHERE t.table_catalog = 'ducklake' "
        )
        if schema:
            schema = _validate_identifier(schema, "schema")
            sql += f"AND t.table_schema = '{schema}' "
        sql += "GROUP BY t.table_schema, t.table_name "
        sql += "ORDER BY t.table_schema, t.table_name"
        return _query_ducklake(sql)
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
        sql = (
            "SELECT column_name, data_type, is_nullable, ordinal_position, "
            "column_default "
            "FROM information_schema.columns "
            f"WHERE table_catalog = 'ducklake' "
            f"AND table_schema = '{schema}' "
            f"AND table_name = '{table}' "
            "ORDER BY ordinal_position"
        )
        rows = _query_ducklake(sql)
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
    settings = DuckLakeSettings()  # type: ignore[missing-argument]
    conn = create_connection(settings)
    try:
        schemas = conn.sql(
            "SELECT DISTINCT table_schema FROM information_schema.tables "
            "WHERE table_catalog = 'ducklake' ORDER BY table_schema"
        ).fetchall()

        result = []
        for (schema_name,) in schemas:
            tables = conn.sql(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_catalog = 'ducklake' AND table_schema = '{schema_name}'"
            ).fetchall()

            total_rows = 0
            for (table_name,) in tables:
                try:
                    cnt = conn.sql(f"SELECT COUNT(*) FROM ducklake.{schema_name}.{table_name}").fetchone()
                    total_rows += cnt[0] if cnt else 0
                except (duckdb.Error, IndexError):
                    logger.warning("Could not count rows in %s.%s", schema_name, table_name)

            result.append(
                {
                    "schema_name": schema_name,
                    "table_count": len(tables),
                    "total_rows": total_rows,
                }
            )

        return result
    finally:
        conn.close()
