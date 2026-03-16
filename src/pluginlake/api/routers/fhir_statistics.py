"""FHIR statistics endpoint.

- ``GET /api/v1/fhir/statistics`` — aggregated FHIR ingestion and clinical statistics
"""

from datetime import UTC, date, datetime
from typing import Any

import duckdb
from fastapi import APIRouter

from pluginlake.core.config import DuckLakeSettings
from pluginlake.core.ducklake.setup import create_connection
from pluginlake.fhir.translator_registry import FHIR_TO_OMOP_TABLE
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/fhir", tags=["fhir"])

_AGE_BOUNDARIES = (18, 30, 45, 60, 75)
_AGE_LABELS = ("0-17", "18-29", "30-44", "45-59", "60-74", "75+")


def _table_row_count(conn: duckdb.DuckDBPyConnection, schema: str, table: str) -> int:
    result = conn.sql(f"SELECT COUNT(*) FROM ducklake.{schema}.{table}")  # noqa: S608 — schema/table from catalog, not user input
    row = result.fetchone()
    return row[0] if row else 0


def _list_tables(conn: duckdb.DuckDBPyConnection, schema: str) -> list[str]:
    result = conn.sql(
        "SELECT table_name FROM information_schema.tables "  # noqa: S608 — schema is internal constant
        f"WHERE table_catalog = 'ducklake' AND table_schema = '{schema}' "
        "ORDER BY table_name"
    )
    return [row[0] for row in result.fetchall()]


def _json_extract_counts(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    json_path: str,
    *,
    limit: int = 0,
) -> dict[str, int]:
    limit_clause = f"LIMIT {limit}" if limit else ""
    rows = conn.sql(
        f"SELECT json_extract_string(json_data, '{json_path}') AS val, COUNT(*) AS cnt "  # noqa: S608 — table/json_path are internal constants
        f"FROM ducklake.fhir_raw.{table} "
        f"WHERE json_extract_string(json_data, '{json_path}') IS NOT NULL "
        f"GROUP BY val ORDER BY cnt DESC {limit_clause}"
    ).fetchall()
    return {str(val): cnt for val, cnt in rows}


def _age_bucket(age: int) -> str:
    for boundary, label in zip(_AGE_BOUNDARIES, _AGE_LABELS, strict=False):
        if age < boundary:
            return label
    return _AGE_LABELS[-1]


def _compute_age_distribution(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    rows = conn.sql(
        "SELECT json_extract_string(json_data, '$.birthDate') AS bd "
        "FROM ducklake.fhir_raw.patient "
        "WHERE json_extract_string(json_data, '$.birthDate') IS NOT NULL"
    ).fetchall()

    buckets: dict[str, int] = dict.fromkeys(_AGE_LABELS, 0)
    today = datetime.now(tz=UTC).date()

    for (bd_str,) in rows:
        try:
            bd = date.fromisoformat(bd_str[:10])
            age = (today - bd).days // 365
        except (ValueError, TypeError):
            continue
        buckets[_age_bucket(age)] += 1

    return buckets


def _count_tables(
    conn: duckdb.DuckDBPyConnection,
    schema: str,
    tables: list[str],
) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    total = 0
    for t in tables:
        try:
            count = _table_row_count(conn, schema, t)
            counts[t] = count
            total += count
        except duckdb.Error:
            logger.warning("Could not count rows in %s.%s", schema, t)
    return counts, total


def _safe_extract(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    json_path: str,
    *,
    limit: int = 0,
) -> dict[str, int]:
    try:
        return _json_extract_counts(conn, table, json_path, limit=limit)
    except duckdb.Error:
        logger.warning("Could not extract %s from %s", json_path, table)
        return {}


def _build_conversion_rates(
    resources_per_type: dict[str, int],
    translated_per_type: dict[str, int],
) -> dict[str, dict[str, int]]:
    rates: dict[str, dict[str, int]] = {}
    for fhir_type, omop_table in FHIR_TO_OMOP_TABLE.items():
        raw_count = resources_per_type.get(fhir_type, 0)
        has_translation = omop_table in translated_per_type
        translated_count = raw_count if has_translation else 0
        if raw_count > 0 or translated_count > 0:
            rates[fhir_type] = {"raw": raw_count, "translated": translated_count}
    return rates


@router.get(
    "/statistics",
    summary="Get FHIR statistics",
    description="Returns aggregated FHIR ingestion metrics and clinical analytics.",
)
def fhir_statistics() -> dict[str, Any]:
    """Return aggregated FHIR statistics."""
    try:
        settings = DuckLakeSettings()  # type: ignore[call-arg] — env-driven fields
        conn = create_connection(settings)
    except Exception:
        logger.exception("Failed to connect to DuckLake")
        return {}

    try:
        raw_tables = _list_tables(conn, "fhir_raw")
        omop_tables = _list_tables(conn, "fhir_omop_raw")

        resources_per_type, total_raw = _count_tables(conn, "fhir_raw", raw_tables)
        translated_per_type, _total_omop = _count_tables(conn, "fhir_omop_raw", omop_tables)
        conversion_rates = _build_conversion_rates(resources_per_type, translated_per_type)
        total_translated = sum(r["translated"] for r in conversion_rates.values())
        overall_conversion = round(total_translated / total_raw * 100, 1) if total_raw > 0 else 0.0

        age_distribution: dict[str, int] = {}
        if "patient" in raw_tables:
            try:
                age_distribution = _compute_age_distribution(conn)
            except duckdb.Error:
                logger.warning("Could not compute age distribution")

        return {
            "total_resources": total_raw,
            "total_translated": total_translated,
            "resource_type_count": len(raw_tables),
            "overall_conversion_pct": overall_conversion,
            "resources_per_type": resources_per_type,
            "translated_per_type": translated_per_type,
            "conversion_rates": conversion_rates,
            "gender_distribution": _safe_extract(conn, "patient", "$.gender") if "patient" in raw_tables else {},
            "age_distribution": age_distribution,
            "top_conditions": (
                _safe_extract(conn, "condition", "$.code.coding[0].display", limit=15)
                if "condition" in raw_tables
                else {}
            ),
            "top_observations": (
                _safe_extract(conn, "observation", "$.code.coding[0].display", limit=15)
                if "observation" in raw_tables
                else {}
            ),
            "encounter_type_distribution": (
                _safe_extract(conn, "encounter", "$.class.code") if "encounter" in raw_tables else {}
            ),
        }
    finally:
        conn.close()
