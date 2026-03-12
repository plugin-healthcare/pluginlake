"""FHIR — resource overview and FHIR-to-OMOP translation mapping."""

import streamlit as st
from backend.catalog import fetch_column_stats
from backend.fhir import FHIR_TO_OMOP_MAPPING, fetch_fhir_omop_tables, fetch_fhir_tables
from client import ApiClient
from components.catalog_detail import render_column_stats

st.title("FHIR")
st.caption("Overview of FHIR resources and their translation to OMOP CDM format.")

client = ApiClient()

# --- FHIR → OMOP mapping --------------------------------------------------

st.header("FHIR → OMOP Mapping")
st.caption(
    "Each FHIR resource type is translated to an OMOP CDM table "
    "using the plugin-rosetta engine. The table below shows which "
    "FHIR resources map to which OMOP tables."
)

mapping_data = [
    {
        "FHIR Resource": resource.replace("_", " ").title(),
        "OMOP Table": info["omop_table"].replace("_", " ").title(),
        "Description": info["description"],
    }
    for resource, info in FHIR_TO_OMOP_MAPPING.items()
]
st.dataframe(mapping_data, use_container_width=True, hide_index=True)

# --- FHIR Raw tables -------------------------------------------------------

st.header("FHIR Raw Data")
st.caption("Raw FHIR NDJSON resources loaded into the catalog.")

fhir_raw = fetch_fhir_tables(client)

if fhir_raw:
    for tbl in fhir_raw:
        name = tbl.get("table_name", "")
        col_count = tbl.get("column_count", "?")
        with st.expander(f"**fhir_raw.{name}** ({col_count} columns)"):
            stats = fetch_column_stats(client, "fhir_raw", name)
            render_column_stats(stats)
else:
    st.info(
        "No FHIR data loaded yet. Upload FHIR NDJSON files on the **Upload Data** page.",
        icon=":material/info:",
    )

# --- FHIR → OMOP translated tables ----------------------------------------

st.header("Translated OMOP Tables")
st.caption("FHIR resources translated into OMOP CDM format.")

fhir_omop = fetch_fhir_omop_tables(client)

if fhir_omop:
    for tbl in fhir_omop:
        name = tbl.get("table_name", "")
        col_count = tbl.get("column_count", "?")
        with st.expander(f"**fhir_omop.{name}** ({col_count} columns)"):
            stats = fetch_column_stats(client, "fhir_omop", name)
            render_column_stats(stats)
else:
    st.info(
        "No translated tables yet. Upload FHIR data and run the translation pipeline.",
        icon=":material/info:",
    )
