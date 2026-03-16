"""UI components for FHIR statistics visualisation."""

from typing import Any

import plotly.graph_objects as go
import streamlit as st

_TEAL = "#0588a6"
_NAVY = "#053c5c"
_ORANGE = "#f28729"
_LIGHT_BLUE = "#bbe2ee"

_CHART_PALETTE = [_TEAL, _NAVY, _ORANGE, _LIGHT_BLUE, "#6fc3d5", "#e8a85c"]

_CHART_LAYOUT: dict[str, Any] = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "sans-serif", "color": _NAVY},
    "margin": {"l": 40, "r": 20, "t": 48, "b": 40},
    "title_font_size": 16,
}


def render_fhir_overview(stats: dict[str, Any]) -> None:
    """Render top-level FHIR KPI cards."""
    if not stats:
        st.info("No FHIR statistics available.", icon=":material/info:")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Resources", f"{stats.get('total_resources', 0):,}")
    c2.metric("Translated Records", f"{stats.get('total_translated', 0):,}")
    c3.metric("Resource Types", stats.get("resource_type_count", "—"))
    c4.metric("Conversion Rate", f"{stats.get('overall_conversion_pct', 0)}%")


def render_resources_per_type(stats: dict[str, Any]) -> None:
    """Horizontal bar chart of raw resource counts per FHIR type."""
    data = stats.get("resources_per_type", {})
    if not data:
        return

    sorted_items = sorted(data.items(), key=lambda x: x[1])
    labels = [t.replace("_", " ").title() for t, _ in sorted_items]
    counts = [c for _, c in sorted_items]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color=_TEAL,
            hovertemplate="%{y}: <b>%{x:,.0f}</b> resources<extra></extra>",
        )
    )
    fig.update_layout(
        **_CHART_LAYOUT,
        title="Resources per Type",
        xaxis_title="Count",
        yaxis_title=None,
        height=max(300, len(labels) * 32 + 80),
    )
    fig.update_xaxes(gridcolor="#e8e8e8")
    st.plotly_chart(fig, width="stretch")


def render_conversion_funnel(stats: dict[str, Any]) -> None:
    """Grouped horizontal bar: raw vs translated per resource type."""
    data = stats.get("conversion_rates", {})
    if not data:
        return

    types = [t.replace("_", " ").title() for t in data]
    raw_counts = [v["raw"] for v in data.values()]
    translated_counts = [v["translated"] for v in data.values()]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=types,
            x=raw_counts,
            name="Raw",
            orientation="h",
            marker_color=_LIGHT_BLUE,
            hovertemplate="%{y}: <b>%{x:,.0f}</b> raw<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=types,
            x=translated_counts,
            name="Translated",
            orientation="h",
            marker_color=_TEAL,
            hovertemplate="%{y}: <b>%{x:,.0f}</b> translated<extra></extra>",
        )
    )
    fig.update_layout(
        **_CHART_LAYOUT,
        title="Conversion Funnel (Raw vs Translated)",
        barmode="group",
        xaxis_title="Count",
        yaxis_title=None,
        height=max(300, len(types) * 48 + 80),
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.06},
    )
    fig.update_layout(margin_t=120)
    fig.update_xaxes(gridcolor="#e8e8e8")
    st.plotly_chart(fig, width="stretch")


def render_fhir_gender(stats: dict[str, Any]) -> None:
    """Donut chart for gender distribution."""
    data = stats.get("gender_distribution", {})
    if not data:
        return

    fig = go.Figure(
        go.Pie(
            labels=list(data.keys()),
            values=list(data.values()),
            hole=0.45,
            marker={"colors": _CHART_PALETTE},
            textinfo="label+percent",
            hovertemplate="%{label}: <b>%{value:,.0f}</b> (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(**_CHART_LAYOUT, title="Gender Distribution", showlegend=False, height=350)
    st.plotly_chart(fig, width="stretch")


def render_age_distribution(stats: dict[str, Any]) -> None:
    """Vertical bar chart for age buckets."""
    data = stats.get("age_distribution", {})
    if not data or all(v == 0 for v in data.values()):
        return

    fig = go.Figure(
        go.Bar(
            x=list(data.keys()),
            y=list(data.values()),
            marker_color=_TEAL,
            hovertemplate="%{x}: <b>%{y:,.0f}</b> patients<extra></extra>",
        )
    )
    fig.update_layout(
        **_CHART_LAYOUT,
        title="Age Distribution",
        xaxis_title="Age Group",
        yaxis_title="Patients",
        height=350,
    )
    fig.update_yaxes(gridcolor="#e8e8e8")
    st.plotly_chart(fig, width="stretch")


def render_top_conditions(stats: dict[str, Any]) -> None:
    """Horizontal bar chart — top 15 conditions."""
    data = stats.get("top_conditions", {})
    if not data:
        return

    sorted_items = sorted(data.items(), key=lambda x: x[1])
    labels = [k for k, _ in sorted_items]
    counts = [c for _, c in sorted_items]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color=_ORANGE,
            hovertemplate="%{y}: <b>%{x:,.0f}</b><extra></extra>",
        )
    )
    fig.update_layout(
        **_CHART_LAYOUT,
        title="Top Conditions",
        xaxis_title="Count",
        yaxis_title=None,
        height=max(350, len(labels) * 28 + 80),
    )
    fig.update_xaxes(gridcolor="#e8e8e8")
    st.plotly_chart(fig, width="stretch")


def render_top_observations(stats: dict[str, Any]) -> None:
    """Horizontal bar chart — top 15 observations."""
    data = stats.get("top_observations", {})
    if not data:
        return

    sorted_items = sorted(data.items(), key=lambda x: x[1])
    labels = [k for k, _ in sorted_items]
    counts = [c for _, c in sorted_items]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color=_NAVY,
            hovertemplate="%{y}: <b>%{x:,.0f}</b><extra></extra>",
        )
    )
    fig.update_layout(
        **_CHART_LAYOUT,
        title="Top Observations",
        xaxis_title="Count",
        yaxis_title=None,
        height=max(350, len(labels) * 28 + 80),
    )
    fig.update_xaxes(gridcolor="#e8e8e8")
    st.plotly_chart(fig, width="stretch")


def render_encounter_distribution(stats: dict[str, Any]) -> None:
    """Donut chart for encounter class distribution."""
    data = stats.get("encounter_type_distribution", {})
    if not data:
        return

    fig = go.Figure(
        go.Pie(
            labels=list(data.keys()),
            values=list(data.values()),
            hole=0.45,
            marker={"colors": _CHART_PALETTE},
            textinfo="label+percent",
            hovertemplate="%{label}: <b>%{value:,.0f}</b> (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(**_CHART_LAYOUT, title="Encounter Class Distribution", showlegend=False, height=350)
    st.plotly_chart(fig, width="stretch")
