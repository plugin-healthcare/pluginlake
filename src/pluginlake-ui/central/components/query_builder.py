"""UI components for the Preset Queries page."""

import streamlit as st

PRESET_QUERIES = {
    "Cohort Count": "Count of unique patients per datastation.",
    "Condition Prevalence": "Top conditions by frequency across all stations.",
    "Demographics Summary": "Age and gender distribution across all stations.",
}


def render_query_selector() -> str | None:
    """Render a dropdown to select a preset query. Returns the selected query name."""
    selected = st.selectbox(
        "Select a preset query",
        options=list(PRESET_QUERIES.keys()),
        index=None,
        placeholder="Choose a query...",
    )

    if selected:
        st.info(PRESET_QUERIES[selected], icon=":material/info:")

    return selected


def render_query_placeholder() -> None:
    """Render a placeholder for query results."""
    st.info(
        "Preset queries will execute federated aggregations across all connected datastations. "
        "Only aggregated results are returned — no patient-level data leaves the datastation.",
        icon=":material/info:",
    )
