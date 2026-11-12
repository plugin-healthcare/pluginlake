"""Start page with links to the web interfaces of the node."""

from html import escape
from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import HTMLResponse

from pluginlake.api.config import HubSettings

router = APIRouter(tags=["hub"])

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>pluginlake</title>
<style>body{{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem}}li{{margin:.6rem 0}}</style>
</head>
<body>
<h1>pluginlake</h1>
<ul>
{items}
</ul>
</body>
</html>
"""


def render_hub(settings: HubSettings, groups: set[str]) -> str:
    """Render the start page with a link for each web interface the user has the role for."""
    items = "\n".join(
        f'<li><a href="https://{escape(name)}.{escape(settings.domain)}/">{escape(title)}</a></li>'
        for name, title in settings.apps.items()
        if name in groups
    )
    return _PAGE.format(items=items)


@router.get("/hub", response_class=HTMLResponse, include_in_schema=False)
def hub(x_auth_request_groups: Annotated[str, Header()] = "") -> str:
    """Return the start page, served on the bare domain of the node.

    The groups header is set by oauth2-proxy through Traefik and holds the Zitadel roles of the user.
    """
    return render_hub(HubSettings(), {group.strip() for group in x_auth_request_groups.split(",")})
