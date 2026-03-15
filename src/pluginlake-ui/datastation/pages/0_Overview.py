"""Overview — pipelines, runs, and data currently on this datastation."""

from datetime import UTC, datetime

import pandas as pd
import streamlit as st
from backend.catalog import fetch_layer_summary
from backend.metadata import fetch_catalog_tables
from backend.pipelines import fetch_assets, fetch_runs
from client import ApiClient

st.title("Overview")

client = ApiClient()

# ── Schema → layer mapping ────────────────────────────────────────────────
# Follows ADR-004 medallion layers + "reference" for controlled vocabularies
# and audit tables that are not patient data.
_LAYER = {
    "omop_raw": "Raw",
    "fhir_raw": "Raw",
    "omop": "Curated",
    "fhir_omop_raw": "Raw",
    "omop_vocab": "Reference",
    "omop_audit": "Reference",
}
_LAYER_ORDER = ["Raw", "Curated", "Reference"]

_DOMAIN = {
    "omop_raw": "OMOP",
    "fhir_raw": "FHIR",
    "omop": "OMOP",
    "fhir_omop_raw": "FHIR",
    "omop_vocab": "OMOP",
    "omop_audit": "OMOP",
}


def _fmt_ts(ts: float | str | None) -> str:
    if ts is None:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return str(ts)


# ── 1. Pipelines & runs ──────────────────────────────────────────────────

st.header("Pipelines")

assets = fetch_assets(client)
runs = fetch_runs(client)

if assets:
    st.caption(f"{len(assets)} registered assets")

    # Build a compact asset table showing the last materialization
    asset_rows = []
    for a in assets:
        key = a.get("key", "")
        parts = key.split("/")
        schema = parts[0] if len(parts) > 1 else "main"
        asset_rows.append(
            {
                "Asset": key,
                "Layer": _LAYER.get(schema, schema),
                "Domain": _DOMAIN.get(schema, "—"),
                "Last Materialized": a.get("last_materialized", "—") or "never",
            }
        )
    st.dataframe(
        pd.DataFrame(asset_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Asset": st.column_config.TextColumn("Asset", width="large"),
            "Layer": st.column_config.TextColumn("Layer", width="small"),
            "Domain": st.column_config.TextColumn("Domain", width="small"),
            "Last Materialized": st.column_config.TextColumn("Last Run", width="medium"),
        },
    )
else:
    st.info("No assets registered yet.", icon=":material/info:")

st.subheader("Recent Runs")

if runs:
    _STATUS_TAG = {
        "SUCCESS": "✅ Success",
        "FAILURE": "❌ Failure",
        "STARTED": "🔄 Started",
        "STARTING": "🔄 Starting",
        "CANCELED": "🚫 Canceled",
    }
    run_rows = []
    for r in runs:
        status = r.get("status", "UNKNOWN")
        run_rows.append(
            {
                "Run ID": r.get("run_id", "—")[:12],
                "Job": r.get("job_name", "—"),
                "Status": _STATUS_TAG.get(status, status),
                "Started": _fmt_ts(r.get("start_time")),
                "Finished": _fmt_ts(r.get("end_time")),
            }
        )
    st.dataframe(
        pd.DataFrame(run_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Run ID": st.column_config.TextColumn("Run ID", width="small"),
            "Job": st.column_config.TextColumn("Job", width="medium"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Started": st.column_config.TextColumn("Started", width="medium"),
            "Finished": st.column_config.TextColumn("Finished", width="medium"),
        },
    )
else:
    st.info("No pipeline runs yet.", icon=":material/info:")


# ── 2. Data in the catalog ───────────────────────────────────────────────

st.header("Data")
st.caption(
    "Tables currently in the catalog, grouped by medallion layer. "
    "Each materialization replaces the table content (full refresh)."
)

tables = fetch_catalog_tables(client)
layer_summary = fetch_layer_summary(client)
rows_by_schema = {s["schema_name"]: s["total_rows"] for s in layer_summary}

if tables:
    # Build a single dataframe with layer + domain tags
    table_rows = []
    for t in tables:
        schema = t.get("table_schema", "")
        table_rows.append(
            {
                "Table": t.get("table_name", ""),
                "Schema": schema,
                "Layer": _LAYER.get(schema, schema),
                "Domain": _DOMAIN.get(schema, "—"),
                "Columns": t.get("column_count", 0),
            }
        )
    df = pd.DataFrame(table_rows)

    # Build tab labels with counts
    tab_labels = []
    tab_layers = []
    for layer_name in _LAYER_ORDER:
        layer_df = df[df["Layer"] == layer_name]
        if layer_df.empty:
            continue
        schemas_in_layer = layer_df["Schema"].unique()
        total_rows = sum(rows_by_schema.get(s, 0) for s in schemas_in_layer)
        tab_labels.append(f"{layer_name}  ({len(layer_df)} tables · {total_rows:,} rows)")
        tab_layers.append(layer_name)

    # Add "Other" tab if there are unmapped schemas
    other_df = df[~df["Layer"].isin(_LAYER_ORDER)]
    if not other_df.empty:
        tab_labels.append(f"Other  ({len(other_df)} tables)")
        tab_layers.append("__other__")

    if tab_labels:
        tabs = st.tabs(tab_labels)
        for tab, layer_name in zip(tabs, tab_layers, strict=True):
            with tab:
                if layer_name == "__other__":
                    layer_df = other_df
                else:
                    layer_df = df[df["Layer"] == layer_name]

                domains = ", ".join(sorted(layer_df["Domain"].unique()))
                st.caption(f"Domains: {domains}")

                st.dataframe(
                    layer_df[["Table", "Schema", "Domain", "Columns"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Table": st.column_config.TextColumn("Table", width="large"),
                        "Schema": st.column_config.TextColumn("Schema", width="medium"),
                        "Domain": st.column_config.TextColumn("Domain", width="small"),
                        "Columns": st.column_config.NumberColumn("Columns", width="small"),
                    },
                )
else:
    st.info(
        "No data in the catalog yet. Go to **Upload Data** to get started.",
        icon=":material/info:",
    )
