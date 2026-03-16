"""Central dashboard — Streamlit entrypoint.

Run with: streamlit run dashboard/central/app.py
"""

from pathlib import Path

import streamlit as st

from config import get_settings

settings = get_settings()

st.set_page_config(
    page_title=settings.page_title,
    page_icon=settings.page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Sidebar ------------------------------------------------------------------

_logo_path = Path(__file__).resolve().parents[3] / "assets" / "logo_plugin_rgb_flavicon.svg"

st.sidebar.title("pluginlake")
if _logo_path.exists():
    st.sidebar.image(str(_logo_path), width=150)
st.sidebar.caption("Central Researcher Dashboard")
st.sidebar.divider()

pages = {
    "Overview": [
        st.Page("pages/1_Station_Overview.py", title="Stations", icon=":material/dns:"),
    ],
    "Analysis": [
        st.Page("pages/2_Preset_Queries.py", title="Preset Queries", icon=":material/query_stats:"),
        st.Page("pages/3_PluginML_Demo.py", title="PluginML Demo", icon=":material/model_training:"),
    ],
}

pg = st.navigation(pages)
pg.run()
