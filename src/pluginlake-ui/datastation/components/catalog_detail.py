"""Column-level statistics display component."""

from typing import Any

import streamlit as st


def render_column_stats(stats: list[dict[str, Any]]) -> None:
    """Render column-level statistics as a rich dataframe.

    Expects rows from DuckDB SUMMARIZE with keys: column_name, column_type,
    min, max, approx_unique, avg, std, q25, q50, q75, count, null_percentage.
    """
    if not stats:
        st.caption("No column statistics available.")
        return

    numeric_types = {
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
        "HUGEINT",
        "INT",
        "REAL",
    }

    display_data = []
    for col in stats:
        null_pct_raw = col.get("null_percentage", "0.00%")
        try:
            null_pct = float(str(null_pct_raw).replace("%", ""))
        except (ValueError, TypeError):
            null_pct = 0.0
        filled_pct = 100.0 - null_pct

        col_type = col.get("column_type", "")
        base_type = col_type.split("(")[0].upper()
        is_numeric = base_type in numeric_types

        display_data.append(
            {
                "Column": col.get("column_name", ""),
                "Type": col_type,
                "Filled %": filled_pct,
                "Unique": col.get("approx_unique", 0),
                "Total": col.get("count", 0),
                "Min": _truncate(col.get("min")) if is_numeric else "—",
                "Max": _truncate(col.get("max")) if is_numeric else "—",
                "Avg": _truncate(col.get("avg")) if is_numeric else "—",
            }
        )

    st.dataframe(
        display_data,
        width="stretch",
        hide_index=True,
        column_config={
            "Column": st.column_config.TextColumn("Column", width="medium"),
            "Type": st.column_config.TextColumn("Type", width="small"),
            "Filled %": st.column_config.ProgressColumn(
                "Filled",
                help="Percentage of non-null values",
                format="%.0f%%",
                min_value=0,
                max_value=100,
            ),
            "Unique": st.column_config.NumberColumn("Unique", format="%d"),
            "Total": st.column_config.NumberColumn("Rows", format="%d"),
            "Min": st.column_config.TextColumn("Min", width="small"),
            "Max": st.column_config.TextColumn("Max", width="small"),
            "Avg": st.column_config.TextColumn("Avg", width="small"),
        },
    )


def _truncate(value: Any, max_len: int = 20) -> str:
    """Truncate a value for display."""
    if value is None:
        return "—"
    s = str(value)
    return s[:max_len] + "…" if len(s) > max_len else s
