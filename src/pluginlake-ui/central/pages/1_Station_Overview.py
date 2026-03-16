"""Station Overview page — health and aggregated stats of all datastations."""

import streamlit as st
from backend.aggregation import (
    aggregate_patient_counts,
    aggregate_records_per_table,
    fetch_all_statistics,
    fetch_station_health,
)
from client import StationPool
from components.station_overview import render_aggregated_metrics, render_station_cards

st.title("Connected Datastations")
st.caption("Health status and aggregated statistics from all connected stations.")

pool = StationPool()

if st.button("Refresh", key="refresh_stations"):
    st.cache_data.clear()

# --- Health ----------------------------------------------------------------

st.header("Station Health")
health = fetch_station_health(pool)
render_station_cards(health)

# --- Aggregated Statistics -------------------------------------------------

st.header("Aggregated Statistics")
all_stats = fetch_all_statistics(pool)

patient_counts = aggregate_patient_counts(all_stats)
render_aggregated_metrics(patient_counts)

records = aggregate_records_per_table(all_stats)
if records:
    st.subheader("Records per OMOP Table (all stations)")
    st.bar_chart(records)
