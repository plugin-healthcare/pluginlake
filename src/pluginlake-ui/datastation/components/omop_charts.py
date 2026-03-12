"""UI components for OMOP statistics visualisation."""

from typing import Any

import plotly.graph_objects as go
import streamlit as st

# Brand colors
_TEAL = "#0588a6"
_NAVY = "#053c5c"
_ORANGE = "#f28729"
_LIGHT_BLUE = "#bbe2ee"

_CHART_PALETTE = [_TEAL, _NAVY, _ORANGE, _LIGHT_BLUE, "#6fc3d5", "#e8a85c"]

_CHART_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "sans-serif", "color": _NAVY},
    "margin": {"l": 40, "r": 20, "t": 48, "b": 40},
    "title_font_size": 16,
}


def render_statistics_overview(stats: dict[str, Any]) -> None:
    """Render top-level OMOP statistics as metric cards."""
    if not stats:
        st.info("No OMOP statistics available.", icon=":material/info:")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Patients", f"{stats.get('total_patients', 0):,}")
    col2.metric("Total Records", f"{stats.get('total_records', 0):,}")
    col3.metric("OMOP Tables", stats.get("table_count", "—"))


def render_records_per_table(stats: dict[str, Any]) -> None:
    """Render a horizontal bar chart of record counts per OMOP table."""
    records_per_table = stats.get("records_per_table", {})
    if not records_per_table:
        return

    # Sort ascending for horizontal bars (largest at top)
    sorted_items = sorted(records_per_table.items(), key=lambda x: x[1])
    tables = [t.replace("_", " ").title() for t, _ in sorted_items]
    counts = [c for _, c in sorted_items]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=tables,
            orientation="h",
            marker_color=_TEAL,
            hovertemplate="%{y}: <b>%{x:,.0f}</b> records<extra></extra>",
        )
    )
    fig.update_layout(
        **_CHART_LAYOUT,
        title="Records per OMOP Table",
        xaxis_title="Record Count",
        yaxis_title=None,
        height=max(300, len(tables) * 32 + 80),
    )
    fig.update_xaxes(gridcolor="#e8e8e8")
    st.plotly_chart(fig, width="stretch")


def render_gender_distribution(stats: dict[str, Any]) -> None:
    """Render gender distribution as a donut chart."""
    gender_dist = stats.get("gender_distribution", {})
    if not gender_dist:
        return

    fig = go.Figure(
        go.Pie(
            labels=list(gender_dist.keys()),
            values=list(gender_dist.values()),
            hole=0.45,
            marker={"colors": _CHART_PALETTE},
            textinfo="label+percent",
            hovertemplate="%{label}: <b>%{value:,.0f}</b> (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        **_CHART_LAYOUT,
        title="Gender Distribution",
        showlegend=False,
        height=350,
    )
    st.plotly_chart(fig, width="stretch")
