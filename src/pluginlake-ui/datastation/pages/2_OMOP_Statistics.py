"""OMOP Statistics page — aggregated data overview."""

import streamlit as st
from backend.statistics import fetch_omop_statistics
from client import ApiClient
from components.omop_charts import (
    render_age_distribution,
    render_gender_distribution,
    render_records_per_table,
    render_statistics_overview,
    render_top_conditions,
    render_top_observations,
)

st.title("OMOP Statistics")
st.caption("Aggregated statistics of OMOP data on this datastation.")

client = ApiClient()

stats = fetch_omop_statistics(client)

# --- Overview metrics ------------------------------------------------------

render_statistics_overview(stats)

# --- Charts ----------------------------------------------------------------

col_left, col_right = st.columns(2)

with col_left:
    render_records_per_table(stats)

with col_right:
    render_gender_distribution(stats)

# --- Demographics ----------------------------------------------------------

if stats.get("age_distribution"):
    st.header("Demographics")
    render_age_distribution(stats)

# --- Clinical Insights -----------------------------------------------------

has_clinical = stats and (stats.get("top_conditions") or stats.get("top_observations"))

if has_clinical:
    st.header("Clinical Insights")
    col_left, col_right = st.columns(2)
    with col_left:
        render_top_conditions(stats)
    with col_right:
        render_top_observations(stats)

# --- Time range ------------------------------------------------------------

if stats.get("observation_period"):
    st.subheader("Observation Period")
    period = stats["observation_period"]
    col1, col2 = st.columns(2)
    col1.metric("Earliest", period.get("start", "—"))
    col2.metric("Latest", period.get("end", "—"))
