"""Metadata page — Dagster assets and DuckLake catalog."""

import streamlit as st
from backend.metadata import fetch_assets, fetch_catalog_columns, fetch_catalog_schemas, fetch_catalog_tables
from client import ApiClient
from components.metadata_view import render_assets_table, render_catalog_tables

st.title("Metadata")
st.caption("Detailed schema and column breakdown for each table in the catalog.")

client = ApiClient()

# --- DuckLake Catalog ------------------------------------------------------

st.header("DuckLake Catalog")
st.caption("Tables and schemas registered in the DuckLake catalog.")

schemas = fetch_catalog_schemas(client)
schema_names = [s.get("schema_name", s) if isinstance(s, dict) else str(s) for s in schemas]

selected_schema = st.selectbox(
    "Filter by schema",
    options=["All", *schema_names],
    index=0,
)

schema_filter = None if selected_schema == "All" else selected_schema
tables = fetch_catalog_tables(client, schema=schema_filter)


def _fetch_columns(schema: str, table: str) -> list[dict]:
    return fetch_catalog_columns(client, schema, table)


render_catalog_tables(tables, fetch_columns_fn=_fetch_columns)

# --- Dagster Assets --------------------------------------------------------

st.header("Dagster Assets")
st.caption("Registered assets with their latest materialization status.")

assets = fetch_assets(client)

materialized_only = st.toggle("Materialized", value=False)
if materialized_only:
    assets = [a for a in assets if a.get("last_materialized")]

render_assets_table(assets)
