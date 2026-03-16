"""Data Catalog — browse tables and inspect column-level statistics."""

import streamlit as st
from backend.catalog import fetch_column_stats
from backend.metadata import fetch_catalog_columns, fetch_catalog_schemas, fetch_catalog_tables
from client import get_client
from components.catalog_detail import render_column_stats

st.title("Data Catalog")
st.caption(
    "Browse all tables and columns in the data lake. Select a table to see its schema and detailed column statistics."
)

client = get_client()

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

# --- Table overview --------------------------------------------------------

st.metric("Tables", len(tables))

table_options = [f"{t.get('table_schema', '')}.{t.get('table_name', '')}" for t in tables]
col_counts = {f"{t.get('table_schema', '')}.{t.get('table_name', '')}": t.get("column_count", "?") for t in tables}

st.dataframe(
    [
        {
            "Table": t.get("table_name", ""),
            "Schema": t.get("table_schema", ""),
            "Columns": t.get("column_count", 0),
        }
        for t in tables
    ],
    width="stretch",
    hide_index=True,
)

# --- Table detail ----------------------------------------------------------

selected = st.selectbox("Inspect table", options=table_options, index=None, placeholder="Select a table...")

if selected:
    schema, name = selected.split(".", 1)
    st.subheader(f"{selected}  ({col_counts.get(selected, '?')} columns)")

    tab_schema, tab_stats = st.tabs(["Schema", "Statistics"])

    with tab_schema:
        columns = fetch_catalog_columns(client, schema, name)
        if columns:
            st.dataframe(
                columns,
                width="stretch",
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
