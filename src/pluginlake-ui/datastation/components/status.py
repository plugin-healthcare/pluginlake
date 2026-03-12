"""Reusable status and health display components."""

import streamlit as st
from client import ApiClient, ApiError


def api_status_badge(client: ApiClient) -> None:
    """Show a colored badge indicating API health."""
    try:
        result = client.health()
        if result.get("status") == "ok":
            st.success("API connected", icon=":material/check_circle:")
        else:
            st.warning("API returned unexpected status", icon=":material/warning:")
    except ApiError as exc:
        st.error(f"API unreachable: {exc.detail}", icon=":material/error:")


def no_data_message(entity: str = "data") -> None:
    """Display a consistent 'no data' placeholder."""
    st.info(f"No {entity} available. The API endpoint may not be implemented yet.", icon=":material/info:")


def error_message(msg: str) -> None:
    """Display a consistent error message."""
    st.error(msg, icon=":material/error:")
