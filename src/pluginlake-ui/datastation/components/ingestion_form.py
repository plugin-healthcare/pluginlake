"""UI components for the Data Ingestion page."""

from datetime import UTC, datetime
from typing import Any

import streamlit as st

# Brand colors
_TEAL = "#0588a6"
_ORANGE = "#f28729"


def _format_timestamp(ts: float | str | None) -> str:
    """Convert epoch seconds or ISO string to readable datetime."""
    if ts is None:
        return "—"
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        return str(ts)
    except (ValueError, OSError):
        return str(ts)


def render_upload_form() -> tuple[Any | None, str]:
    """Render the file upload form. Returns (uploaded_file, dataset_name)."""
    with st.form("upload_form", clear_on_submit=True):
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["csv", "json", "parquet", "ndjson", "xlsx"],
            help="Supported formats: CSV, JSON, Parquet, NDJSON, XLSX",
        )
        dataset = st.text_input(
            "Dataset name",
            placeholder="e.g. patients, condition_occurrence",
            help="Target dataset or OMOP table name.",
        )
        submitted = st.form_submit_button("Upload", type="primary", width="stretch")

    if submitted and uploaded_file and dataset:
        return uploaded_file, dataset
    return None, ""


def render_ingestion_runs(runs: list[dict[str, Any]]) -> None:
    """Render recent ingestion runs with status indicators."""
    if not runs:
        st.info("No recent ingestion runs.", icon=":material/info:")
        return

    st.metric("Recent Runs", len(runs))

    display_data = []
    for run in runs:
        status = run.get("status", "UNKNOWN").upper()
        display_data.append(
            {
                "Job": run.get("job_name", "—"),
                "Status": status,
                "Started": _format_timestamp(run.get("start_time")),
                "Finished": _format_timestamp(run.get("end_time")),
                "Run ID": run.get("run_id", "—"),
            }
        )

    st.dataframe(
        display_data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(
                "Status",
                help="Dagster run status",
            ),
            "Run ID": st.column_config.TextColumn(
                "Run ID",
                help="Dagster run identifier",
                width="small",
            ),
        },
    )
