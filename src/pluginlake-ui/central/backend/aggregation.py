"""Backend logic for aggregating statistics across datastations."""

import logging
from typing import Any

import streamlit as st
from client import StationPool

logger = logging.getLogger(__name__)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_station_health(_pool: StationPool) -> dict[str, dict[str, Any]]:
    """Check health of all configured datastations."""
    return _pool.health_check_all()


@st.cache_data(ttl=120, show_spinner=False)
def fetch_all_statistics(_pool: StationPool) -> dict[str, dict[str, Any]]:
    """Fetch OMOP statistics from all stations."""
    return _pool.fetch_all_statistics()


def aggregate_patient_counts(station_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Sum patient counts across all reachable stations.

    Returns:
        Dictionary with total_patients and per-station breakdown.
    """
    total = 0
    per_station: dict[str, int] = {}

    for url, result in station_stats.items():
        if result.get("status") != "ok":
            continue
        data = result.get("data", {})
        count = data.get("total_patients", 0)
        total += count
        per_station[url] = count

    return {
        "total_patients": total,
        "per_station": per_station,
    }


def aggregate_records_per_table(station_stats: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Sum record counts per OMOP table across all reachable stations."""
    combined: dict[str, int] = {}

    for result in station_stats.values():
        if result.get("status") != "ok":
            continue
        records = result.get("data", {}).get("records_per_table", {})
        for table, count in records.items():
            combined[table] = combined.get(table, 0) + count

    return combined
