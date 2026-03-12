"""Backend logic for the Pipelines page."""

import logging
from typing import Any

import streamlit as st
from client import ApiClient, ApiError

logger = logging.getLogger(__name__)


@st.cache_data(ttl=30, show_spinner=False)
def fetch_assets(_client: ApiClient) -> list[dict[str, Any]]:
    """Fetch Dagster assets with materialization status."""
    try:
        return _client.get_assets()
    except ApiError:
        logger.exception("Failed to fetch assets")
        return []


@st.cache_data(ttl=15, show_spinner=False)
def fetch_runs(_client: ApiClient) -> list[dict[str, Any]]:
    """Fetch recent Dagster runs."""
    try:
        return _client.get_ingestion_runs()
    except ApiError:
        logger.exception("Failed to fetch runs")
        return []
