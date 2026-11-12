"""Sidebar links to the other web interfaces of the node, filtered by the roles of the user."""

from urllib.parse import quote

import streamlit as st

from config import DashboardSettings


def visible_links(settings: DashboardSettings, groups: set[str]) -> dict[str, str]:
    """Return label and URL of each web interface the user has the role for."""
    return {
        label: f"https://{name}.{settings.domain}/{'docs' if name == 'api' else ''}"
        for name, label in {**settings.apps, "api": "API documentation"}.items()
        if name in groups
    }


def sign_out_url(settings: DashboardSettings) -> str:
    """Return the URL that ends the oauth2-proxy session and then the identity provider session."""
    end_session = quote(f"https://auth.{settings.domain}/oidc/v1/end_session", safe="")
    return f"https://console.{settings.domain}/oauth2/sign_out?rd={end_session}"


def sidebar_links(settings: DashboardSettings) -> None:
    """Show a link for each web interface the signed-in user has a role for.

    The roles come from the groups header that oauth2-proxy sets through Traefik.
    """
    groups = {group.strip() for group in st.context.headers.get("X-Auth-Request-Groups", "").split(",")}
    for label, url in visible_links(settings, groups).items():
        st.link_button(label, url, icon=":material/open_in_new:", width="stretch")
    st.link_button("Sign out", sign_out_url(settings), icon=":material/logout:", width="stretch")
