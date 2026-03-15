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
    "fhir_omop_raw": {"label": "FHIR \u2192 OMOP (staging)", "color": _ORANGE, "standard": "FHIR"},
}

_FLOW_EDGES = [
    ("omop_raw", "omop", _TEAL),
    ("omop_vocab", "omop", _NAVY),
    ("fhir_raw", "fhir_omop_raw", _ORANGE),
    ("fhir_omop_raw", "omop", _ORANGE),
]


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"rgba({r},{g},{b},{alpha})"


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

    node_labels: list[str] = []
    node_colors: list[str] = []
    node_hover: list[str] = []
    node_index: dict[str, int] = {}

    for schema in active:
        name = schema["schema_name"]
        info = _LAYER_INFO.get(name, {"label": name, "color": _GRAY})
        rows = schema["total_rows"]
        tables = schema["table_count"]
        node_index[name] = len(node_labels)
        node_labels.append(info["label"])
        node_colors.append(_hex_to_rgba(info.get("color", _GRAY), 0.8))
        node_hover.append(f"<b>{info['label']}</b><br>{tables} tables<br>{rows:,} rows")

    sources: list[int] = []
    targets: list[int] = []
    values: list[int] = []
    link_colors: list[str] = []
    link_hover: list[str] = []

    for src, tgt, color in _FLOW_EDGES:
        if src in node_index and tgt in node_index:
            tgt_rows = schema_map.get(tgt, {}).get("total_rows", 0)
            flow_value = max(tgt_rows, 1)
            sources.append(node_index[src])
            targets.append(node_index[tgt])
            values.append(flow_value)
            link_colors.append(_hex_to_rgba(color, 0.25))
            src_label = _LAYER_INFO.get(src, {"label": src})["label"]
            tgt_label = _LAYER_INFO.get(tgt, {"label": tgt})["label"]
            link_hover.append(f"{src_label} \u2192 {tgt_label}<br>{flow_value:,} rows")

    if not sources:
        st.info(
            "Not enough data to show the flow diagram. Load data into at least two connected layers.",
            icon=":material/info:",
        )
        return

    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            textfont={"family": "sans-serif", "color": "white", "size": 13},
            node={
                "pad": 40,
                "thickness": 18,
                "label": node_labels,
                "color": node_colors,
                "hovertemplate": "%{customdata}<extra></extra>",
                "customdata": node_hover,
                "line": {"width": 0},
            },
            link={
                "source": sources,
                "target": targets,
                "value": values,
                "color": link_colors,
                "hovertemplate": "%{customdata}<extra></extra>",
                "customdata": link_hover,
            },
        )
    )
    fig.update_layout(
        font={"family": "sans-serif", "color": _NAVY, "size": 13},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 24, "r": 24, "t": 16, "b": 16},
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)
