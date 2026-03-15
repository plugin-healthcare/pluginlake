"""FHIR — ingestion statistics, clinical analytics, and FHIR-to-OMOP mapping."""

import streamlit as st
from backend.catalog import fetch_column_stats
from backend.fhir import (
    FHIR_TO_OMOP_MAPPING,
    fetch_fhir_omop_tables,
    fetch_fhir_statistics,
    fetch_fhir_tables,
)
from client import ApiClient
from components.catalog_detail import render_column_stats
from components.fhir_charts import (
    render_age_distribution,
    render_conversion_funnel,
    render_encounter_distribution,
    render_fhir_gender,
    render_fhir_overview,
    render_resources_per_type,
    render_top_conditions,
    render_top_observations,
)

st.title("FHIR")
st.caption("Ingestion metrics, clinical analytics, and FHIR-to-OMOP translation.")

client = ApiClient()
stats = fetch_fhir_statistics(client)

# --- A. Ingestion Overview ---------------------------------------------------

st.header("Ingestion Overview")

if stats:
    render_fhir_overview(stats)

    col_left, col_right = st.columns(2)
    with col_left:
        render_resources_per_type(stats)
    with col_right:
        render_conversion_funnel(stats)
else:
    st.info(
        "No FHIR data loaded yet. Upload FHIR NDJSON files on the **Upload Data** page.",
        icon=":material/info:",
    )

# --- B. Patient Demographics -------------------------------------------------

if stats and (stats.get("gender_distribution") or stats.get("age_distribution")):
    st.header("Patient Demographics")
    col_left, col_right = st.columns(2)
    with col_left:
        render_fhir_gender(stats)
    with col_right:
        render_age_distribution(stats)

# --- C. Clinical Insights ----------------------------------------------------

has_clinical = stats and (
    stats.get("top_conditions") or stats.get("top_observations") or stats.get("encounter_type_distribution")
)

if has_clinical:
    st.header("Clinical Insights")
    col_left, col_right = st.columns(2)
    with col_left:
        render_top_conditions(stats)
    with col_right:
        render_top_observations(stats)
    render_encounter_distribution(stats)

# --- D. Reference ------------------------------------------------------------

st.header("Reference")

with st.expander("FHIR → OMOP Mapping"):
    st.caption("Each FHIR resource type is translated to an OMOP CDM table using the plugin-rosetta engine.")
    mapping_data = [
        {
            "FHIR Resource": resource.replace("_", " ").title(),
            "OMOP Table": info["omop_table"].replace("_", " ").title(),
            "Description": info["description"],
        }
        for resource, info in FHIR_TO_OMOP_MAPPING.items()
    ]
    st.dataframe(mapping_data, use_container_width=True, hide_index=True)

with st.expander("FHIR Raw Tables"):
    fhir_raw = fetch_fhir_tables(client)
    if fhir_raw:
        st.caption("Each table stores raw FHIR JSON resources in a single `json_data` column.")
        st.dataframe(
            [{"Table": f"fhir_raw.{t['table_name']}"} for t in fhir_raw],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No FHIR raw tables found.", icon=":material/info:")

with st.expander("Translated OMOP Tables"):
    fhir_omop = fetch_fhir_omop_tables(client)
    if fhir_omop:
        for tbl in fhir_omop:
            name = tbl.get("table_name", "")
            col_count = tbl.get("column_count", "?")
            st.markdown(f"**fhir_omop_raw.{name}** ({col_count} columns)")
            col_stats = fetch_column_stats(client, "fhir_omop_raw", name)
            render_column_stats(col_stats)
    else:
        st.info("No translated OMOP tables found.", icon=":material/info:")
