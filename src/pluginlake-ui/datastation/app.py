"""Datastation dashboard — Streamlit entrypoint.

Run with: streamlit run dashboard/datastation/app.py
"""

from datetime import UTC, datetime
from pathlib import Path

import streamlit as st
from client import ApiClient
from components.status import api_status_badge

from config import get_settings

settings = get_settings()

st.set_page_config(
    page_title=settings.page_title,
    page_icon=settings.page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Logo & branding ----------------------------------------------------------

_logo_path = Path(__file__).resolve().parents[3] / "assets" / "logo_plugin_rgb_flavicon.svg"
if _logo_path.exists():
    st.logo(str(_logo_path))

st.markdown(
    """
    <style>
    [data-testid="stLogo"] img { height: 3.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Navigation ---------------------------------------------------------------

pages = [
    st.Page("pages/1_Metadata.py", title="Metadata", icon=":material/database:"),
    st.Page("pages/2_OMOP_Statistics.py", title="OMOP Statistics", icon=":material/analytics:"),
    st.Page("pages/3_Data_Ingestion.py", title="Data Ingestion", icon=":material/upload:"),
]

pg = st.navigation(pages, position="top")

# --- Sidebar ------------------------------------------------------------------

st.sidebar.title("pluginlake")
st.sidebar.caption("Datastation Dashboard")

if "last_refreshed" not in st.session_state:
    st.session_state.last_refreshed = datetime.now(UTC)

if st.sidebar.button("Refresh", icon=":material/refresh:", width="stretch"):
    st.cache_data.clear()
    st.session_state.last_refreshed = datetime.now(UTC)
    st.rerun()

st.sidebar.caption(f"Last updated: {st.session_state.last_refreshed:%H:%M:%S}")

with st.sidebar:
    api_status_badge(ApiClient())

pg.run()
