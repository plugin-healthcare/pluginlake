"""Preset Queries page — federated aggregated queries (Nice to Have)."""

import streamlit as st
from components.query_builder import render_query_placeholder, render_query_selector

st.title("Preset Queries")
st.caption("Execute predefined aggregated queries across connected datastations.")

# --- Query selector --------------------------------------------------------

selected = render_query_selector()

st.divider()

if selected:
    st.subheader(f"Results: {selected}")
    st.warning(
        "This feature is not yet implemented. "
        "When ready, it will federate the query to all datastations, "
        "execute locally, and return only aggregated results.",
        icon=":material/construction:",
    )
else:
    render_query_placeholder()
