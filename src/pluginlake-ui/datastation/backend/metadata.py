"""Backend logic for the Metadata page.

Fetches Dagster asset metadata and DuckLake catalog information
from the pluginlake API and reshapes it for display.
"""

import logging
from typing import Any

import streamlit as st
from client import ApiClient, ApiError

logger = logging.getLogger(__name__)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_assets(_client: ApiClient) -> list[dict[str, Any]]:
    """Fetch Dagster assets with materialization status."""
    try:
        return _client.get_assets()
    except ApiError:
        logger.exception("Failed to fetch assets")
        return []


@st.cache_data(ttl=60, show_spinner=False)
def fetch_catalog_tables(_client: ApiClient, schema: str | None = None) -> list[dict[str, Any]]:
    """Fetch DuckLake catalog tables."""
    try:
        return _client.get_catalog_tables(schema=schema)
    except ApiError:
        logger.exception("Failed to fetch catalog tables")
        return []


@st.cache_data(ttl=60, show_spinner=False)
def fetch_catalog_schemas(_client: ApiClient) -> list[dict[str, Any]]:
    """Fetch DuckLake schemas."""
    try:
        return _client.get_catalog_schemas()
    except ApiError:
        logger.exception("Failed to fetch catalog schemas")
        return []


@st.cache_data(ttl=60, show_spinner=False)
def fetch_catalog_columns(_client: ApiClient, schema: str, table: str) -> list[dict[str, Any]]:
    """Fetch column metadata for a specific DuckLake table."""
    try:
        return _client.get_catalog_columns(schema=schema, table=table)
    except ApiError:
        logger.exception("Failed to fetch columns for %s.%s", schema, table)
        return []
