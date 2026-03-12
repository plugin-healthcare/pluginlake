"""OMOP statistics endpoint.

- ``GET /api/v1/omop/statistics`` — aggregated OMOP table statistics
"""

from typing import Any

import duckdb
from fastapi import APIRouter

from pluginlake.core.config import DuckLakeSettings
from pluginlake.core.ducklake.setup import create_connection
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/omop", tags=["omop"])

_GENDER_MAP = {
    8507: "Male",
    8532: "Female",
    8521: "Other",
}


def _get_omop_tables(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """List all tables in the omop schema."""
    result = conn.sql(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_catalog = 'ducklake' AND table_schema = 'omop' "
        "ORDER BY table_name"
    )
    return [row[0] for row in result.fetchall()]


def _get_row_count(conn: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Get row count for a DuckLake OMOP table."""
    result = conn.sql(f"SELECT COUNT(*) FROM ducklake.omop.{table_name}")  # noqa: S608
    row = result.fetchone()
    return row[0] if row else 0


@router.get(
    "/statistics",
    summary="Get OMOP statistics",
    description="Returns aggregated statistics across all OMOP tables.",
)
def omop_statistics() -> dict[str, Any]:
    """Return aggregated OMOP statistics."""
    try:
        settings = DuckLakeSettings()  # type: ignore[missing-argument]
        conn = create_connection(settings)
    except Exception:
        logger.exception("Failed to connect to DuckLake")
        return {}

    try:
        tables = _get_omop_tables(conn)
        if not tables:
            return {"total_patients": 0, "total_records": 0, "table_count": 0, "records_per_table": {}}

        records_per_table: dict[str, int] = {}
        total_records = 0
        for table in tables:
            try:
                count = _get_row_count(conn, table)
                records_per_table[table] = count
                total_records += count
            except duckdb.Error:
                logger.warning("Could not count rows in omop.%s", table)
                records_per_table[table] = 0

        total_patients = records_per_table.get("person", 0)

        # Gender distribution from person table
        gender_distribution: dict[str, int] = {}
        if "person" in tables:
            try:
                rows = conn.sql(
                    "SELECT gender_concept_id, COUNT(*) AS cnt FROM ducklake.omop.person GROUP BY gender_concept_id"
                ).fetchall()
                for concept_id, count in rows:
                    label = _GENDER_MAP.get(concept_id, "Unknown")
                    gender_distribution[label] = count
            except duckdb.Error:
                logger.warning("Could not compute gender distribution")

        return {
            "total_patients": total_patients,
            "total_records": total_records,
            "table_count": len(tables),
            "records_per_table": records_per_table,
            "gender_distribution": gender_distribution,
        }
    finally:
        conn.close()
