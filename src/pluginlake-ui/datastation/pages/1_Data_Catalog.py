"""Data Catalog — browse tables and inspect column-level statistics."""

import streamlit as st
from backend.catalog import fetch_column_stats
from backend.metadata import fetch_catalog_columns, fetch_catalog_schemas, fetch_catalog_tables
from client import ApiClient
from components.catalog_detail import render_column_stats

st.title("Data Catalog")
st.caption(
    "Browse all tables and columns in the data lake. Select a table to see its schema and detailed column statistics."
)

client = ApiClient()

# --- Schema filter ---------------------------------------------------------

schemas = fetch_catalog_schemas(client)
schema_names = [s.get("schema_name", s) if isinstance(s, dict) else str(s) for s in schemas]

selected_schema = st.selectbox(
    "Filter by layer",
    options=["All", *schema_names],
    index=0,
)

schema_filter = None if selected_schema == "All" else selected_schema
tables = fetch_catalog_tables(client, schema=schema_filter)

if not tables:
    st.info("No tables found. Ingest data to populate the catalog.", icon=":material/info:")
    st.stop()

# --- Table list with expandable detail ------------------------------------

st.metric("Tables", len(tables))

for tbl in tables:
    schema = tbl.get("table_schema", "")
    name = tbl.get("table_name", "")
    col_count = tbl.get("column_count", "?")
    label = f"**{schema}.{name}**  ({col_count} columns)"

    with st.expander(label, expanded=False):
        tab_schema, tab_stats = st.tabs(["Schema", "Statistics"])

        with tab_schema:
            columns = fetch_catalog_columns(client, schema, name)
            if columns:
                st.dataframe(
                    columns,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "column_name": st.column_config.TextColumn("Column"),
                        "data_type": st.column_config.TextColumn("Type"),
                        "is_nullable": st.column_config.TextColumn("Nullable"),
                        "ordinal_position": st.column_config.NumberColumn("#", format="%d"),
                    },
                )
            else:
                st.caption("No schema information available.")

        with tab_stats:
            stats = fetch_column_stats(client, schema, name)
            render_column_stats(stats)
