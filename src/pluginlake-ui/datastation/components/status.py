"""Reusable status and health display components."""

import streamlit as st
from client import ApiClient, ApiError


@st.cache_data(ttl=30, show_spinner=False)
def _check_health(_client: ApiClient) -> tuple[str, str]:
    """Return (level, message) for the API health badge."""
    try:
        result = _client.health()
    except ApiError as exc:
        return "error", f"API unreachable: {exc.detail}"
    else:
        if result.get("status") == "ok":
            return "success", "API connected"
        return "warning", "API returned unexpected status"


def api_status_badge(client: ApiClient) -> None:
    """Show a colored badge indicating API health."""
    level, message = _check_health(client)
    icon_map = {"success": ":material/check_circle:", "warning": ":material/warning:", "error": ":material/error:"}
    getattr(st, level)(message, icon=icon_map[level])


def no_data_message(entity: str = "data") -> None:
    """Display a consistent 'no data' placeholder."""
    st.info(f"No {entity} available. The API endpoint may not be implemented yet.", icon=":material/info:")


def error_message(msg: str) -> None:
    """Display a consistent error message."""
    st.error(msg, icon=":material/error:")
