"""First-run bootstrap of the edge stack (``pluginlake-init``).

Runs once after Zitadel is healthy and removes the manual setup steps:

1. Waits for the admin machine token that Zitadel writes on first start.
2. Creates (or finds) the Zitadel project and the OIDC application for oauth2-proxy.
3. Makes sure every protected hostname has a redirect URI.
4. Writes the oauth2-proxy config file with the client credentials and cookie secret.

The run is idempotent: existing credentials in the config file are reused, and a new client
secret is only generated when the file is missing or belongs to another client.
"""

import json
import secrets
import sys
import time
from pathlib import Path

import httpx

from pluginlake.deploy.config_bootstrap import BootstrapSettings
from pluginlake.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)

_API = "/management/v1"


def wait_for_file(path: Path, timeout: int) -> str:
    """Wait until a non-empty file exists and return its stripped content.

    Raises:
        TimeoutError: If the file does not appear within ``timeout`` seconds.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file() and path.read_text().strip():
            return path.read_text().strip()
        time.sleep(2)
    msg = f"{path} did not appear within {timeout}s"
    raise TimeoutError(msg)


def wait_for_zitadel(client: httpx.Client, timeout: int) -> None:
    """Wait until the Zitadel management API accepts the admin token.

    Raises:
        TimeoutError: If Zitadel does not answer within ``timeout`` seconds.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if client.get(f"{_API}/orgs/me").status_code == httpx.codes.OK:
                return
        except httpx.TransportError:
            pass
        time.sleep(2)
    msg = f"Zitadel did not accept the admin token within {timeout}s"
    raise TimeoutError(msg)


def redirect_uris(hosts: list[str]) -> list[str]:
    """Return the OAuth callback URL for each protected host."""
    return [f"https://{host}/oauth2/callback" for host in hosts]


def _first_id(response: httpx.Response) -> str | None:
    response.raise_for_status()
    result = response.json().get("result") or []
    return result[0]["id"] if result else None


def _name_query(name: str) -> dict:
    return {"queries": [{"nameQuery": {"name": name, "method": "TEXT_QUERY_METHOD_EQUALS"}}]}


def ensure_project(client: httpx.Client, name: str) -> str:
    """Return the id of the project, creating it when missing."""
    project_id = _first_id(client.post(f"{_API}/projects/_search", json=_name_query(name)))
    if project_id:
        return project_id
    response = client.post(f"{_API}/projects", json={"name": name})
    response.raise_for_status()
    logger.info("Created Zitadel project %r", name)
    return response.json()["id"]


def ensure_app(
    client: httpx.Client,
    project_id: str,
    name: str,
    hosts: list[str],
) -> tuple[str, str, str | None]:
    """Return ``(app_id, client_id, client_secret)`` for the OIDC app.

    The secret is only returned for a newly created app, because Zitadel never shows it again.
    """
    base = f"{_API}/projects/{project_id}/apps"
    app_id = _first_id(client.post(f"{base}/_search", json=_name_query(name)))
    if app_id:
        current = client.get(f"{base}/{app_id}")
        current.raise_for_status()
        return app_id, current.json()["app"]["oidcConfig"]["clientId"], None

    response = client.post(
        f"{base}/oidc",
        json={
            "name": name,
            "redirectUris": redirect_uris(hosts),
            "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
            "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"],
            "appType": "OIDC_APP_TYPE_WEB",
            "authMethodType": "OIDC_AUTH_METHOD_TYPE_BASIC",
        },
    )
    response.raise_for_status()
    body = response.json()
    logger.info("Created OIDC app %r", name)
    return body["appId"], body["clientId"], body["clientSecret"]


def sync_redirect_uris(client: httpx.Client, project_id: str, app_id: str, hosts: list[str]) -> None:
    """Add missing redirect URIs and allowed origins to the app, keeping existing ones."""
    url = f"{_API}/projects/{project_id}/apps/{app_id}"
    current = client.get(url)
    current.raise_for_status()
    config = current.json()["app"]["oidcConfig"]

    uris = sorted({*config["redirectUris"], *redirect_uris(hosts)})
    origins = sorted({*(config.get("allowedOrigins") or []), *(f"https://{h}" for h in hosts)})
    if uris == sorted(config["redirectUris"]) and origins == sorted(config.get("allowedOrigins") or []):
        logger.info("Redirect URIs already up to date")
        return

    response = client.put(
        f"{url}/oidc_config",
        json={
            "redirectUris": uris,
            "responseTypes": config["responseTypes"],
            "grantTypes": config["grantTypes"],
            "appType": "OIDC_APP_TYPE_WEB",
            "authMethodType": "OIDC_AUTH_METHOD_TYPE_BASIC",
            "devMode": config.get("devMode", False),
            "allowedOrigins": origins,
        },
    )
    response.raise_for_status()
    logger.info("Updated redirect URIs: %s", ", ".join(uris))


def new_client_secret(client: httpx.Client, project_id: str, app_id: str) -> str:
    """Generate a fresh client secret for an existing app."""
    response = client.post(f"{_API}/projects/{project_id}/apps/{app_id}/oidc_config/_generate_client_secret", json={})
    response.raise_for_status()
    return response.json()["clientSecret"]


def read_proxy_config(path: Path) -> dict[str, str]:
    """Read the ``key = "value"`` lines of an existing oauth2-proxy config file."""
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition(" = ")
        if separator:
            values[key] = json.loads(value)
    return values


def write_proxy_config(path: Path, client_id: str, client_secret: str, cookie_secret: str) -> None:
    """Write the oauth2-proxy config file readable by its owner only."""
    lines = [
        f"client_id = {json.dumps(client_id)}",
        f"client_secret = {json.dumps(client_secret)}",
        f"cookie_secret = {json.dumps(cookie_secret)}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o644)  # read by the non-root proxy user, the volume is not shared with other services


def bootstrap(client: httpx.Client, settings: BootstrapSettings) -> None:
    """Provision the OIDC app and write the oauth2-proxy config."""
    hosts = settings.protected_hosts
    project_id = ensure_project(client, settings.project_name)
    app_id, client_id, client_secret = ensure_app(client, project_id, settings.app_name, hosts)
    sync_redirect_uris(client, project_id, app_id, hosts)

    existing = read_proxy_config(settings.proxy_config_file)
    cookie_secret = existing.get("cookie_secret") or secrets.token_hex(16)
    if client_secret is None:
        if existing.get("client_id") == client_id and existing.get("client_secret"):
            client_secret = existing["client_secret"]
        else:
            client_secret = new_client_secret(client, project_id, app_id)
            logger.info("Generated a new client secret for %r", settings.app_name)

    write_proxy_config(settings.proxy_config_file, client_id, client_secret, cookie_secret)
    logger.info("Wrote %s", settings.proxy_config_file)


def main() -> int:
    """Entry point of the ``pluginlake-init`` container."""
    setup_logging()
    settings = BootstrapSettings()
    token = wait_for_file(settings.admin_pat_file, settings.wait_seconds)
    headers = {"Authorization": f"Bearer {token}", "Host": settings.auth_host}
    with httpx.Client(base_url=settings.zitadel_url, headers=headers, timeout=30) as client:
        wait_for_zitadel(client, settings.wait_seconds)
        bootstrap(client, settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
