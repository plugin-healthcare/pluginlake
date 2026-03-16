"""Backend logic for the OMOP Statistics page.

Fetches aggregated OMOP statistics from the pluginlake API
and prepares DataFrames for chart rendering.
"""

import logging
from typing import Any

import streamlit as st
from client import ApiClient, ApiError

logger = logging.getLogger(__name__)


@st.cache_data(ttl=120, show_spinner="Loading OMOP statistics...")
def fetch_omop_statistics(_client: ApiClient) -> dict[str, Any]:
    """Fetch aggregated OMOP statistics."""
    try:
        return _client.get_omop_statistics()
    except ApiError:
        logger.exception("Failed to fetch OMOP statistics")
        return {}
