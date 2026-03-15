"""OMOP statistics endpoint.

- ``GET /api/v1/omop/statistics`` — aggregated OMOP table statistics
"""

from datetime import UTC, datetime
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

_AGE_BOUNDARIES = (18, 30, 45, 60, 75)
_AGE_LABELS = ("0-17", "18-29", "30-44", "45-59", "60-74", "75+")


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
    result = conn.sql(f"SELECT COUNT(*) FROM ducklake.omop.{table_name}")  # noqa: S608 — table name from catalog
    row = result.fetchone()
    return row[0] if row else 0


def _age_bucket(age: int) -> str:
    for boundary, label in zip(_AGE_BOUNDARIES, _AGE_LABELS, strict=False):
        if age < boundary:
            return label
    return _AGE_LABELS[-1]


def _compute_age_distribution(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    rows = conn.sql("SELECT year_of_birth FROM ducklake.omop.person WHERE year_of_birth IS NOT NULL").fetchall()

    buckets: dict[str, int] = dict.fromkeys(_AGE_LABELS, 0)
    current_year = datetime.now(tz=UTC).year

    for (yob,) in rows:
        try:
            age = current_year - int(yob)
        except (ValueError, TypeError):
            continue
        if age < 0:
            continue
        buckets[_age_bucket(age)] += 1

    return buckets


def _count_tables(conn: duckdb.DuckDBPyConnection, tables: list[str]) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    total = 0
    for table in tables:
        try:
            count = _get_row_count(conn, table)
            counts[table] = count
            total += count
        except duckdb.Error:
            logger.warning("Could not count rows in omop.%s", table)
            counts[table] = 0
    return counts, total


def _gender_distribution(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    rows = conn.sql(
        "SELECT gender_concept_id, gender_source_value, COUNT(*) AS cnt "
        "FROM ducklake.omop.person GROUP BY gender_concept_id, gender_source_value"
    ).fetchall()
    result: dict[str, int] = {}
    for concept_id, source_value, count in rows:
        label = _GENDER_MAP.get(concept_id) or (source_value or "Unknown").capitalize()
        result[label] = result.get(label, 0) + count
    return result


def _safe_query(fn, label: str) -> dict[str, int]:  # noqa: ANN001 — accepts any callable returning dict
    try:
        return fn()
    except duckdb.Error:
        logger.warning("Could not compute %s", label)
        return {}


def _top_concept_names(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    concept_id_col: str,
    source_value_col: str,
    *,
    limit: int = 15,
) -> dict[str, int]:
    try:
        rows = conn.sql(
            f"SELECT COALESCE(c.concept_name, t.{source_value_col}, CAST(t.{concept_id_col} AS VARCHAR)) AS val, "  # noqa: S608 — table/columns are internal constants
            f"COUNT(*) AS cnt "
            f"FROM ducklake.omop.{table} t "
            f"LEFT JOIN ducklake.omop_vocab.concept c ON t.{concept_id_col} = c.concept_id "
            f"WHERE t.{concept_id_col} IS NOT NULL AND t.{concept_id_col} != 0 "
            f"GROUP BY val ORDER BY cnt DESC LIMIT {limit}"
        ).fetchall()
    except duckdb.Error:
        rows = conn.sql(
            f"SELECT COALESCE({source_value_col}, CAST({concept_id_col} AS VARCHAR)) AS val, COUNT(*) AS cnt "  # noqa: S608
            f"FROM ducklake.omop.{table} "
            f"WHERE {concept_id_col} IS NOT NULL AND {concept_id_col} != 0 "
            f"GROUP BY val ORDER BY cnt DESC LIMIT {limit}"
        ).fetchall()
    return {str(val): cnt for val, cnt in rows}


@router.get(
    "/statistics",
    summary="Get OMOP statistics",
    description="Returns aggregated statistics across all OMOP tables.",
)
def omop_statistics() -> dict[str, Any]:
    """Return aggregated OMOP statistics."""
    try:
        settings = DuckLakeSettings()  # type: ignore[missing-argument] — env-driven fields
        conn = create_connection(settings)
    except Exception:
        logger.exception("Failed to connect to DuckLake")
        return {}

    try:
        tables = _get_omop_tables(conn)
        if not tables:
            return {"total_patients": 0, "total_records": 0, "table_count": 0, "records_per_table": {}}

        records_per_table, total_records = _count_tables(conn, tables)

        return {
            "total_patients": records_per_table.get("person", 0),
            "total_records": total_records,
            "table_count": len(tables),
            "records_per_table": records_per_table,
            "gender_distribution": (
                _safe_query(lambda: _gender_distribution(conn), "gender distribution") if "person" in tables else {}
            ),
            "age_distribution": (
                _safe_query(lambda: _compute_age_distribution(conn), "age distribution") if "person" in tables else {}
            ),
            "top_conditions": (
                _safe_query(
                    lambda: _top_concept_names(
                        conn, "condition_occurrence", "condition_concept_id", "condition_source_value"
                    ),
                    "top conditions",
                )
                if "condition_occurrence" in tables
                else {}
            ),
            "top_observations": (
                _safe_query(
                    lambda: _top_concept_names(
                        conn, "observation", "observation_concept_id", "observation_source_value"
                    ),
                    "top observations",
                )
                if "observation" in tables
                else {}
            ),
        }
    finally:
        conn.close()
