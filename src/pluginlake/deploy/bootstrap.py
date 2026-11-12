"""First-run bootstrap of the edge stack (``pluginlake-init``).

Runs once after Zitadel is healthy and removes the manual setup steps:

1. Waits for the admin machine token that Zitadel writes on first start.
2. Creates (or finds) the Zitadel project and the OIDC application for oauth2-proxy.
3. Makes sure every protected hostname has a redirect URI.
4. Creates a project role per application, a webhook target that exposes the roles of a user
   as ``groups`` claim, and grants the first admin all roles.
5. Writes the oauth2-proxy config file with the client credentials and cookie secret.

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
_ACTIONS = "/v2/actions"
_GROUPS_TARGET = "groups-claim"
# Token functions in which the target adds the ``groups`` claim.
_GROUPS_FUNCTIONS = ("preuserinfo", "preaccesstoken")


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


def assert_project_roles(client: httpx.Client, project_id: str, name: str) -> None:
    """Make Zitadel add the roles of the user to the tokens of this project."""
    response = client.get(f"{_API}/projects/{project_id}")
    response.raise_for_status()
    if response.json()["project"].get("projectRoleAssertion"):
        return
    client.put(f"{_API}/projects/{project_id}", json={"name": name, "projectRoleAssertion": True}).raise_for_status()
    logger.info("Enabled role assertion for project %r", name)


def ensure_roles(client: httpx.Client, project_id: str, roles: list[str]) -> list[str]:
    """Create the project roles that do not exist yet and return the created ones."""
    response = client.post(f"{_API}/projects/{project_id}/roles/_search", json={})
    response.raise_for_status()
    existing = {role["key"] for role in response.json().get("result") or []}
    created = [role for role in roles if role not in existing]
    for role in created:
        client.post(
            f"{_API}/projects/{project_id}/roles", json={"roleKey": role, "displayName": role}
        ).raise_for_status()
        logger.info("Created role %r", role)
    return created


def ensure_groups_target(client: httpx.Client, endpoint: str, key_file: Path) -> str:
    """Return the id of the call target that adds the ``groups`` claim, creating it when needed.

    The target is created with ``interruptOnError`` so that Zitadel refuses to issue a token when
    the webhook fails. The signing key is written to ``key_file`` for the webhook service.
    """
    search = {"filters": [{"targetNameFilter": {"targetName": _GROUPS_TARGET}}]}
    response = client.post(f"{_ACTIONS}/targets/search", json=search)
    response.raise_for_status()
    found = (response.json().get("targets") or [None])[0]
    if found is None:
        body = {
            "name": _GROUPS_TARGET,
            "endpoint": endpoint,
            "timeout": "5s",
            "restCall": {"interruptOnError": True},
        }
        created = client.post(f"{_ACTIONS}/targets", json=body)
        created.raise_for_status()
        target_id, key = created.json()["id"], created.json()["signingKey"]
        logger.info("Created target %r", _GROUPS_TARGET)
    else:
        target_id, key = found["id"], found["signingKey"]
        if found["endpoint"] != endpoint:
            client.patch(f"{_ACTIONS}/targets/{target_id}", json={"endpoint": endpoint}).raise_for_status()
            logger.info("Updated endpoint of target %r", _GROUPS_TARGET)
    if not key_file.is_file() or key_file.read_text().strip() != key:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key + "\n")
        key_file.chmod(0o644)  # read by the non-root webhook user, the volume is not shared with other services
        logger.info("Wrote %s", key_file)
    return target_id


def ensure_groups_executions(client: httpx.Client, target_id: str) -> None:
    """Call the target in the token functions that carry the ``groups`` claim."""
    for function in _GROUPS_FUNCTIONS:
        client.put(
            f"{_ACTIONS}/executions",
            json={"condition": {"function": {"name": function}}, "targets": [target_id]},
        ).raise_for_status()


def grant_admin_roles(
    client: httpx.Client, project_id: str, admin_username: str, roles: list[str], new_roles: list[str]
) -> None:
    """Give the first admin all roles, or only the newly created roles when the admin already has a grant.

    Roles the admin has since given up are not granted again.
    """
    query = {
        "queries": [{"userNameQuery": {"userName": f"{admin_username}@", "method": "TEXT_QUERY_METHOD_STARTS_WITH"}}]
    }
    response = client.post(f"{_API}/users/_search", json=query)
    response.raise_for_status()
    users = [user for user in response.json().get("result") or [] if "human" in user]
    if not users:
        logger.warning("Admin user %r not found, no roles granted", admin_username)
        return
    user_id = users[0]["id"]
    grants = client.post(
        f"{_API}/users/grants/_search",
        json={"queries": [{"userIdQuery": {"userId": user_id}}, {"projectIdQuery": {"projectId": project_id}}]},
    )
    grants.raise_for_status()
    existing = grants.json().get("result")
    if existing:
        missing = [role for role in new_roles if role not in existing[0].get("roleKeys", [])]
        if missing:
            keys = [*existing[0].get("roleKeys", []), *missing]
            client.put(f"{_API}/users/{user_id}/grants/{existing[0]['id']}", json={"roleKeys": keys}).raise_for_status()
            logger.info("Granted new roles %s to %r", ", ".join(missing), admin_username)
        return
    client.post(f"{_API}/users/{user_id}/grants", json={"projectId": project_id, "roleKeys": roles}).raise_for_status()
    logger.info("Granted roles %s to %r", ", ".join(roles), admin_username)


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
    assert_project_roles(client, project_id, settings.project_name)
    new_roles = ensure_roles(client, project_id, settings.protected_subdomains)
    target_id = ensure_groups_target(client, settings.groups_hook_url, settings.groups_hook_key_file)
    ensure_groups_executions(client, target_id)
    grant_admin_roles(client, project_id, settings.admin_username, settings.protected_subdomains, new_roles)

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
