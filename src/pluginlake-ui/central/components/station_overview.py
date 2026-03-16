"""UI components for the Station Overview page."""

from typing import Any

import streamlit as st


def render_station_cards(health: dict[str, dict[str, Any]]) -> None:
    """Render a card per datastation with health status."""
    if not health:
        st.warning("No datastations configured.", icon=":material/warning:")
        st.info("Set `DASHBOARD_CENTRAL_STATION_URLS` to a comma-separated list of datastation API URLs.")
        return

    cols = st.columns(min(len(health), 4))
    for idx, (url, status) in enumerate(health.items()):
        col = cols[idx % len(cols)]
        with col:
            is_ok = status.get("status") == "ok"
            icon = ":material/check_circle:" if is_ok else ":material/error:"
            color = "green" if is_ok else "red"

            st.markdown(f"### :{color}[{icon}] Station {idx + 1}")
            st.caption(url)

            if not is_ok:
                st.error(status.get("error", "Unreachable"))


def render_aggregated_metrics(patient_counts: dict[str, Any]) -> None:
    """Render aggregated patient count metrics."""
    total = patient_counts.get("total_patients", 0)
    per_station = patient_counts.get("per_station", {})

    st.metric("Total Patients (all stations)", f"{total:,}")

    if per_station:
        st.subheader("Per Station")
        cols = st.columns(min(len(per_station), 4))
        for idx, (url, count) in enumerate(per_station.items()):
            cols[idx % len(cols)].metric(f"Station {idx + 1}", f"{count:,}", help=url)
