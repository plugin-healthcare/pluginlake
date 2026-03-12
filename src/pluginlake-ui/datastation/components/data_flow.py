"""Data flow Sankey diagram component."""

from typing import Any

import plotly.graph_objects as go
import streamlit as st

_TEAL = "#0588a6"
_NAVY = "#053c5c"
_ORANGE = "#f28729"
_LIGHT_BLUE = "#bbe2ee"
_GRAY = "#cccccc"

_LAYER_INFO = {
    "omop_raw": {"label": "OMOP Raw", "color": _LIGHT_BLUE, "standard": "OMOP"},
    "omop_vocab": {"label": "Vocabularies", "color": _NAVY, "standard": "OMOP"},
    "omop": {"label": "OMOP Validated", "color": _TEAL, "standard": "OMOP"},
    "omop_audit": {"label": "Audit Log", "color": _GRAY, "standard": "OMOP"},
    "fhir_raw": {"label": "FHIR Raw", "color": "#f2a965", "standard": "FHIR"},
    "fhir_omop": {"label": "FHIR → OMOP", "color": _ORANGE, "standard": "FHIR"},
}

# Directed edges: (source_schema, target_schema, color)
_FLOW_EDGES = [
    ("omop_raw", "omop", _TEAL),
    ("omop_vocab", "omop", _NAVY),
    ("fhir_raw", "fhir_omop", _ORANGE),
]


def render_data_flow(layer_summary: list[dict[str, Any]]) -> None:
    """Render a Sankey diagram showing data flow between layers."""
    schema_map = {s["schema_name"]: s for s in layer_summary}

    active = [s for s in layer_summary if s["total_rows"] > 0 or s["table_count"] > 0]
    if not active:
        st.info(
            "No data in the catalog yet. Ingest data to see the flow diagram.",
            icon=":material/info:",
        )
        return

    # Build nodes
    node_labels: list[str] = []
    node_colors: list[str] = []
    node_index: dict[str, int] = {}

    for schema in active:
        name = schema["schema_name"]
        info = _LAYER_INFO.get(name, {"label": name, "color": _GRAY})
        rows = schema["total_rows"]
        tables = schema["table_count"]
        label = f"{info['label']}\n{tables} tables · {rows:,} rows"
        node_index[name] = len(node_labels)
        node_labels.append(label)
        node_colors.append(info.get("color", _GRAY))

    # Build links
    sources: list[int] = []
    targets: list[int] = []
    values: list[int] = []
    link_colors: list[str] = []

    for src, tgt, color in _FLOW_EDGES:
        if src in node_index and tgt in node_index:
            tgt_rows = schema_map.get(tgt, {}).get("total_rows", 0)
            sources.append(node_index[src])
            targets.append(node_index[tgt])
            values.append(max(tgt_rows, 1))
            link_colors.append(color + "80")

    if not sources:
        st.info(
            "Not enough data to show the flow diagram. Load data into at least two connected layers.",
            icon=":material/info:",
        )
        return

    fig = go.Figure(
        go.Sankey(
            node={
                "pad": 20,
                "thickness": 20,
                "label": node_labels,
                "color": node_colors,
            },
            link={
                "source": sources,
                "target": targets,
                "value": values,
                "color": link_colors,
            },
        )
    )
    fig.update_layout(
        title="Data Flow Between Layers",
        font={"family": "sans-serif", "color": _NAVY, "size": 13},
        paper_bgcolor="rgba(0,0,0,0)",
        margin={"l": 20, "r": 20, "t": 48, "b": 20},
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)
