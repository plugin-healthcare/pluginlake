"""Pipelines — data flow visualization and run history."""

from datetime import UTC, datetime

import streamlit as st
from backend.catalog import fetch_layer_summary
from backend.pipelines import fetch_assets, fetch_runs
from client import get_client
from components.data_flow import render_data_flow

_RUN_ID_DISPLAY_LEN = 12

st.title("Pipelines")
st.caption("See how data flows through the system and monitor processing runs.")

client = get_client()

# --- Data flow diagram -----------------------------------------------------

st.header("Data Flow")
st.caption(
    "This diagram shows how data moves between layers. "
    "Raw data is ingested, validated against vocabularies, "
    "and transformed into analytics-ready formats."
)

layer_summary = fetch_layer_summary(client)
render_data_flow(layer_summary)

# --- Asset status ----------------------------------------------------------

st.header("Assets")
st.caption("Each asset represents a data table managed by the processing pipeline.")

assets = fetch_assets(client)

if assets:
    materialized = sum(1 for a in assets if a.get("last_materialized"))
    pending = len(assets) - materialized

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Assets", len(assets))
    col2.metric("Materialized", materialized)
    col3.metric("Pending", pending)

    display = [
        {
            "Asset": a.get("key", ""),
            "Group": a.get("group", ""),
            "Status": "✅ Materialized" if a.get("last_materialized") else "⏳ Pending",
            "Last Run": a.get("last_materialized", "—"),
        }
        for a in assets
    ]
    st.dataframe(display, width="stretch", hide_index=True)
else:
    st.info(
        "No assets registered. Start the Dagster pipeline to create assets.",
        icon=":material/info:",
    )

# --- Recent runs -----------------------------------------------------------

st.header("Recent Runs")
st.caption("History of pipeline processing runs.")

runs = fetch_runs(client)

if runs:

    def _fmt_ts(ts: float | str | None) -> str:
        if ts is None:
            return "—"
        try:
            return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            return str(ts)

    display_runs = [
        {
            "Job": r.get("job_name", "—"),
            "Status": r.get("status", "UNKNOWN"),
            "Started": _fmt_ts(r.get("start_time")),
            "Finished": _fmt_ts(r.get("end_time")),
            "Run ID": (r.get("run_id", "—")[:_RUN_ID_DISPLAY_LEN] + "…")
            if len(r.get("run_id", "")) > _RUN_ID_DISPLAY_LEN
            else r.get("run_id", "—"),
        }
        for r in runs
    ]
    st.dataframe(display_runs, width="stretch", hide_index=True)
else:
    st.info("No runs recorded yet.", icon=":material/info:")
