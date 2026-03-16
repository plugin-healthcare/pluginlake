"""Backend logic for the Data Catalog page."""

import logging
from typing import Any

import streamlit as st
from client import ApiClient, ApiError

logger = logging.getLogger(__name__)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_column_stats(_client: ApiClient, schema: str, table: str) -> list[dict[str, Any]]:
    """Fetch column-level statistics for a table."""
    try:
        return _client.get_column_stats(schema=schema, table=table)
    except ApiError:
        logger.exception("Failed to fetch column stats for %s.%s", schema, table)
        return []


@st.cache_data(ttl=60, show_spinner=False)
def fetch_layer_summary(_client: ApiClient) -> list[dict[str, Any]]:
    """Fetch per-schema layer summary."""
    try:
        return _client.get_layer_summary()
    except ApiError:
        logger.exception("Failed to fetch layer summary")
        return []
