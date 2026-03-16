"""Backend logic for the Data Ingestion page.

Handles file uploads and fetches ingestion run history
from the pluginlake API.
"""

import logging
from typing import Any

import streamlit as st
from client import ApiClient, ApiError

logger = logging.getLogger(__name__)


@st.cache_data(ttl=30, show_spinner=False)
def fetch_ingestion_info(_client: ApiClient) -> dict[str, Any]:
    """Fetch ingestion configuration (allowed extensions, max size)."""
    try:
        return _client.get_ingestion_info()
    except ApiError:
        logger.exception("Failed to fetch ingestion info")
        return {}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_ingestion_runs(_client: ApiClient) -> list[dict[str, Any]]:
    """Fetch recent ingestion runs."""
    try:
        return _client.get_ingestion_runs()
    except ApiError:
        logger.exception("Failed to fetch ingestion runs")
        return []


def upload_file(client: ApiClient, file_bytes: bytes, filename: str, dataset: str) -> dict[str, Any]:
    """Upload a file and return the ingestion response. Not cached."""
    return client.upload_file(file_bytes, filename, dataset)


def upload_omop_csv(client: ApiClient, file_bytes: bytes, filename: str, table_name: str) -> dict[str, Any]:
    """Upload an OMOP CSV and return the ingestion response. Not cached."""
    return client.upload_omop_csv(file_bytes, filename, table_name)
