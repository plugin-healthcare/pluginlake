"""UI components for the Metadata page."""

from collections.abc import Callable
from typing import Any

import streamlit as st

# Brand colors
_TEAL = "#0588a6"
_NAVY = "#053c5c"
_ORANGE = "#f28729"
_LIGHT_BLUE = "#bbe2ee"


def _status_pill(value: str | None) -> str:
    """Return an HTML status pill for materialization status."""
    if value:
        return f'<span style="background:{_TEAL};color:#fff;padding:2px 10px;border-radius:12px;font-size:0.82rem;">Materialized</span>'
    return '<span style="background:#e0e0e0;color:#666;padding:2px 10px;border-radius:12px;font-size:0.82rem;">Pending</span>'


def render_assets_table(assets: list[dict[str, Any]]) -> None:
    """Render Dagster assets as styled cards with status indicators."""
    if not assets:
        st.info("No assets found.", icon=":material/info:")
        return

    # Summary metrics
    total = len(assets)
    materialized = sum(1 for a in assets if a.get("last_materialized"))
    pending = total - materialized

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Assets", total)
    col2.metric("Materialized", materialized)
    col3.metric("Pending", pending)

    st.markdown("")  # spacer

    # Render each asset with expandable column details
    for asset in assets:
        key = asset.get("key", "—")
        group = asset.get("group", "")
        status = "Materialized" if asset.get("last_materialized") else "Pending"
        last_run = asset.get("last_materialized", "—")
        columns = asset.get("columns", [])
        col_count = len(columns)

        label = f"**{key}**"
        if group:
            label += f"  \u2014  {group}"
        label += f"  \u2014  {status}"
        if col_count:
            label += f"  ({col_count} columns)"

        with st.expander(label, expanded=False):
            info_col1, info_col2 = st.columns(2)
            info_col1.caption(f"Status: **{status}**")
            info_col2.caption(f"Last run: {last_run}")

            desc = asset.get("description", "")
            if desc:
                st.caption(desc)

            if columns:
                st.dataframe(
                    columns,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "name": st.column_config.TextColumn("Column"),
                        "type": st.column_config.TextColumn("Type"),
                        "description": st.column_config.TextColumn("Description"),
                    },
                )
            else:
                st.caption("No column metadata available for this asset.")


def render_catalog_tables(
    tables: list[dict[str, Any]],
    fetch_columns_fn: Callable[[str, str], list[dict[str, Any]]] | None = None,
) -> None:
    """Render DuckLake catalog tables with expandable column details.

    Args:
        tables: List of table dicts with table_schema, table_name, column_count.
        fetch_columns_fn: Callable(schema, table) -> list[dict] to lazy-load columns.
    """
    if not tables:
        st.info("No catalog tables found.", icon=":material/info:")
        return

    # Summary metric
    st.metric("Tables in Catalog", len(tables))

    for tbl in tables:
        schema = tbl.get("table_schema", "")
        name = tbl.get("table_name", "")
        col_count = tbl.get("column_count", "?")
        label = f"**{schema}.{name}**  ({col_count} columns)"

        with st.expander(label, expanded=False):
            if fetch_columns_fn:
                columns = fetch_columns_fn(schema, name)
                if columns:
                    st.dataframe(
                        columns,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "column_name": st.column_config.TextColumn("Column"),
                            "data_type": st.column_config.TextColumn("Type"),
                            "is_nullable": st.column_config.TextColumn("Nullable"),
                            "ordinal_position": st.column_config.NumberColumn("Position", format="%d"),
                            "column_default": st.column_config.TextColumn("Default"),
                        },
                    )
                else:
                    st.caption("No column information available.")
            else:
                st.caption("Column detail loading not configured.")
