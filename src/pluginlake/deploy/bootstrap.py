"""First-run bootstrap of the edge stack (``pluginlake-init``).

Runs once after Zitadel is healthy and removes the manual setup steps:

1. Waits for the admin machine token that Zitadel writes on first start.
2. Creates (or finds) the Zitadel project and the OIDC application for oauth2-proxy.
3. Makes sure every protected hostname has a redirect URI and the app may refresh its tokens.
4. Creates a project role per application, a webhook target that exposes the roles of a user
   as ``groups`` claim, and grants the first admin all roles.
5. Limits how long a sign-in lasts by the lifetime of the refresh token and of the credential checks.
6. Writes the oauth2-proxy config file with the client credentials and cookie secret.

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
from pluginlake.utils.secrets import replace_secret

logger = get_logger(__name__)

_API = "/management/v1"
_ACTIONS = "/v2/actions"
_ADMIN = "/admin/v1"
_GROUPS_TARGET = "groups-claim"
# Token functions in which the target adds the ``groups`` claim.
_GROUPS_FUNCTIONS = ("preuserinfo", "preaccesstoken")
# How long each kind of credential check keeps a user signed in at Zitadel.
_CHECK_LIFETIMES = (
    "passwordCheckLifetime",
    "externalLoginCheckLifetime",
    "secondFactorCheckLifetime",
    "multiFactorCheckLifetime",
)
# The writable fields of the login policy, which an update replaces as a whole.
_LOGIN_POLICY = (
    "allowUsernamePassword",
    "allowRegister",
    "allowExternalIdp",
    "forceMfa",
    "passwordlessType",
    "hidePasswordReset",
    "ignoreUnknownUsernames",
    "defaultRedirectUri",
    "mfaInitSkipLifetime",
    "allowDomainDiscovery",
    "disableLoginWithEmail",
    "disableLoginWithPhone",
    "forceMfaLocalOnly",
)


def wait_for_file(path: Path, timeout: int) -> str:
    """Wait until a non-empty file exists and return its stripped content.

    Args:
        path: The file to wait for.
        timeout: Seconds to wait before giving up.

    Returns:
        The stripped content of the file.

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


def redirect_uris(hosts: list[str]) -> list[str]:
    """Return the OAuth callback URL for each protected host.

    Args:
        hosts: Public hostnames behind the forward-auth proxy.

    Returns:
        One callback URL per host.
    """
    return [f"https://{host}/oauth2/callback" for host in hosts]


def read_proxy_config(path: Path) -> dict[str, str]:
    """Read the ``key = "value"`` lines of an existing oauth2-proxy config file.

    Args:
        path: The config file, which may not exist yet.

    Returns:
        The values by key, empty when the file is missing.
    """
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition(" = ")
        if separator:
            values[key] = json.loads(value)
    return values


# The refresh token lets oauth2-proxy renew the session, and with it the ``groups`` claim, without a new login.
_GRANT_TYPES = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE", "OIDC_GRANT_TYPE_REFRESH_TOKEN"]
# Writable settings of an OIDC app, as the Management API returns them in ``oidcConfig``.
_OIDC_SETTINGS = [
    "responseTypes",
    "appType",
    "authMethodType",
    "postLogoutRedirectUris",
    "devMode",
    "accessTokenType",
    "accessTokenRoleAssertion",
    "idTokenRoleAssertion",
    "idTokenUserinfoAssertion",
    "clockSkew",
    "skipNativeAppSuccessPage",
    "backChannelLogoutUri",
    "loginVersion",
]


def write_proxy_config(path: Path, client_id: str, client_secret: str, cookie_secret: str) -> bool:
    """Atomically write the oauth2-proxy config file, readable by the non-root proxy user.

    An interrupted run leaves the previous file intact, so the next run still finds the credentials.

    Args:
        path: The config file to write.
        client_id: OIDC client id of the proxy.
        client_secret: OIDC client secret of the proxy.
        cookie_secret: Secret that signs the session cookie.

    Returns:
        True if the file was created or changed, False if it already held this config.
    """
    lines = [
        f"client_id = {json.dumps(client_id)}",
        f"client_secret = {json.dumps(client_secret)}",
        f"cookie_secret = {json.dumps(cookie_secret)}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    # The volume is not shared with other services.
    return replace_secret(path, "\n".join(lines) + "\n", mode=0o644)


def _first_id(response: httpx.Response) -> str | None:
    response.raise_for_status()
    result = response.json().get("result") or []
    return result[0]["id"] if result else None


def _name_query(name: str) -> dict:
    return {"queries": [{"nameQuery": {"name": name, "method": "TEXT_QUERY_METHOD_EQUALS"}}]}


class ZitadelBootstrap:
    """Provision Zitadel for the edge stack through its API.

    The client and the settings are fixed at construction. The class keeps no other state, so
    every step looks up what it needs and can be repeated safely.
    """

    def __init__(self, client: httpx.Client, settings: BootstrapSettings) -> None:
        """Set up the provisioner.

        Args:
            client: HTTP client with the base URL and the admin token of Zitadel.
            settings: Names, hosts and file locations of this node.
        """
        self.client = client
        self.settings = settings

    def wait_until_ready(self) -> None:
        """Wait until the Zitadel management API accepts the admin token.

        Raises:
            TimeoutError: If Zitadel does not answer within ``wait_seconds``.
        """
        timeout = self.settings.wait_seconds
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.client.get(f"{_API}/orgs/me").status_code == httpx.codes.OK:
                    return
            except httpx.TransportError:
                pass
            time.sleep(2)
        msg = f"Zitadel did not accept the admin token within {timeout}s"
        raise TimeoutError(msg)

    def ensure_project(self) -> str:
        """Find the project, or create it when missing.

        Returns:
            The id of the project.
        """
        name = self.settings.project_name
        project_id = _first_id(self.client.post(f"{_API}/projects/_search", json=_name_query(name)))
        if project_id:
            return project_id
        response = self.client.post(f"{_API}/projects", json={"name": name})
        response.raise_for_status()
        logger.info("Created Zitadel project %r", name)
        return response.json()["id"]

    def ensure_app(self, project_id: str) -> tuple[str, str, str | None]:
        """Find the OIDC app of the proxy, or create it when missing.

        Args:
            project_id: The project that owns the app.

        Returns:
            ``(app_id, client_id, client_secret)``. The secret is only returned for a newly
            created app, because Zitadel never shows it again.
        """
        name = self.settings.app_name
        base = f"{_API}/projects/{project_id}/apps"
        app_id = _first_id(self.client.post(f"{base}/_search", json=_name_query(name)))
        if app_id:
            current = self.client.get(f"{base}/{app_id}")
            current.raise_for_status()
            return app_id, current.json()["app"]["oidcConfig"]["clientId"], None

        response = self.client.post(
            f"{base}/oidc",
            json={
                "name": name,
                "redirectUris": redirect_uris(self.settings.protected_hosts),
                "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
                "grantTypes": _GRANT_TYPES,
                "appType": "OIDC_APP_TYPE_WEB",
                "authMethodType": "OIDC_AUTH_METHOD_TYPE_BASIC",
            },
        )
        response.raise_for_status()
        body = response.json()
        logger.info("Created OIDC app %r", name)
        return body["appId"], body["clientId"], body["clientSecret"]

    def sync_app_config(self, project_id: str, app_id: str) -> None:
        """Add missing redirect URIs, allowed origins and grant types to the app, keeping existing ones.

        Args:
            project_id: The project that owns the app.
            app_id: The OIDC app of the proxy.
        """
        hosts = self.settings.protected_hosts
        url = f"{_API}/projects/{project_id}/apps/{app_id}"
        current = self.client.get(url)
        current.raise_for_status()
        config = current.json()["app"]["oidcConfig"]

        uris = sorted({*config["redirectUris"], *redirect_uris(hosts)})
        origins = sorted({*(config.get("additionalOrigins") or []), *(f"https://{h}" for h in hosts)})
        grant_types = sorted({*config["grantTypes"], *_GRANT_TYPES})
        if (
            uris == sorted(config["redirectUris"])
            and origins == sorted(config.get("additionalOrigins") or [])
            and grant_types == sorted(config["grantTypes"])
        ):
            logger.info("OIDC app config already up to date")
            return

        # The update replaces every setting, so the ones an operator changed are sent back as they are.
        kept = {key: config[key] for key in _OIDC_SETTINGS if key in config}
        response = self.client.put(
            f"{url}/oidc_config",
            json={**kept, "redirectUris": uris, "grantTypes": grant_types, "additionalOrigins": origins},
        )
        response.raise_for_status()
        logger.info("Updated OIDC app: redirect URIs %s, grant types %s", ", ".join(uris), ", ".join(grant_types))

    def assert_project_roles(self, project_id: str) -> None:
        """Make Zitadel add the roles of the user to the tokens of this project.

        Args:
            project_id: The project to change.
        """
        name = self.settings.project_name
        response = self.client.get(f"{_API}/projects/{project_id}")
        response.raise_for_status()
        if response.json()["project"].get("projectRoleAssertion"):
            return
        self.client.put(
            f"{_API}/projects/{project_id}", json={"name": name, "projectRoleAssertion": True}
        ).raise_for_status()
        logger.info("Enabled role assertion for project %r", name)

    def ensure_roles(self, project_id: str) -> list[str]:
        """Create the role of each protected application that does not exist yet.

        Args:
            project_id: The project that owns the roles.

        Returns:
            The roles that were created.
        """
        response = self.client.post(f"{_API}/projects/{project_id}/roles/_search", json={})
        response.raise_for_status()
        existing = {role["key"] for role in response.json().get("result") or []}
        created = [role for role in self.settings.protected_roles if role not in existing]
        for role in created:
            self.client.post(
                f"{_API}/projects/{project_id}/roles", json={"roleKey": role, "displayName": role}
            ).raise_for_status()
            logger.info("Created role %r", role)
        return created

    def ensure_groups_target(self) -> str:
        """Find the call target that adds the ``groups`` claim, or create it when missing.

        The target is created with ``interruptOnError`` so that Zitadel refuses to issue a token
        when the webhook fails. The signing key is written to ``groups_hook_key_file`` for the
        webhook service.

        Returns:
            The id of the target.
        """
        endpoint = self.settings.groups_hook_url
        key_file = self.settings.groups_hook_key_file
        search = {"filters": [{"targetNameFilter": {"targetName": _GROUPS_TARGET}}]}
        response = self.client.post(f"{_ACTIONS}/targets/search", json=search)
        response.raise_for_status()
        found = (response.json().get("targets") or [None])[0]
        if found is None:
            body = {
                "name": _GROUPS_TARGET,
                "endpoint": endpoint,
                "timeout": "5s",
                "restCall": {"interruptOnError": True},
            }
            created = self.client.post(f"{_ACTIONS}/targets", json=body)
            created.raise_for_status()
            target_id, key = created.json()["id"], created.json()["signingKey"]
            logger.info("Created target %r", _GROUPS_TARGET)
        else:
            target_id, key = found["id"], found["signingKey"]
            if found["endpoint"] != endpoint:
                self.client.post(f"{_ACTIONS}/targets/{target_id}", json={"endpoint": endpoint}).raise_for_status()
                logger.info("Updated endpoint of target %r", _GROUPS_TARGET)
        if not key_file.is_file() or key_file.read_text().strip() != key:
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_text(key + "\n")
            key_file.chmod(0o644)  # the volume is not shared with other services
            logger.info("Wrote %s", key_file)
        return target_id

    def ensure_groups_executions(self, target_id: str) -> None:
        """Call the target in the token functions that carry the ``groups`` claim.

        Setting an execution replaces its whole list of targets, so targets that an operator added are kept, in their
        order, and the groups target is appended when it is missing.

        Args:
            target_id: The id of the target from ``ensure_groups_target``.
        """
        for function in _GROUPS_FUNCTIONS:
            condition = {"function": {"name": function}}
            search = {"filters": [{"inConditionsFilter": {"conditions": [condition]}}]}
            response = self.client.post(f"{_ACTIONS}/executions/search", json=search)
            response.raise_for_status()
            executions = response.json().get("executions") or []
            targets = list(executions[0].get("targets") or []) if executions else []
            if target_id in targets:
                continue
            self.client.put(
                f"{_ACTIONS}/executions", json={"condition": condition, "targets": [*targets, target_id]}
            ).raise_for_status()
            logger.info("Added target %r to the %s execution", _GROUPS_TARGET, function)

    def grant_admin_roles(self, project_id: str, new_roles: list[str]) -> None:
        """Give the first admin all roles once, and later only the newly created roles.

        Roles the admin has since given up, or a grant that was deleted, are not granted again.

        Args:
            project_id: The project that owns the roles.
            new_roles: The roles that were created in this run.
        """
        admin_username = self.settings.admin_username
        roles = self.settings.protected_roles
        query = {
            "queries": [
                {"userNameQuery": {"userName": f"{admin_username}@", "method": "TEXT_QUERY_METHOD_STARTS_WITH"}}
            ]
        }
        response = self.client.post(f"{_API}/users/_search", json=query)
        response.raise_for_status()
        users = [user for user in response.json().get("result") or [] if "human" in user]
        if not users:
            logger.warning("Admin user %r not found, no roles granted", admin_username)
            return
        user_id = users[0]["id"]
        grants = self.client.post(
            f"{_API}/users/grants/_search",
            json={"queries": [{"userIdQuery": {"userId": user_id}}, {"projectIdQuery": {"projectId": project_id}}]},
        )
        grants.raise_for_status()
        existing = grants.json().get("result")
        marker = self.settings.admin_granted_file
        if existing:
            marker.touch()
            missing = [role for role in new_roles if role not in existing[0].get("roleKeys", [])]
            if missing:
                keys = [*existing[0].get("roleKeys", []), *missing]
                self.client.put(
                    f"{_API}/users/{user_id}/grants/{existing[0]['id']}", json={"roleKeys": keys}
                ).raise_for_status()
                logger.info("Granted new roles %s to %r", ", ".join(missing), admin_username)
            return
        if marker.exists():
            logger.info("The grant of %r was removed on purpose, not granting it again", admin_username)
            return
        self.client.post(
            f"{_API}/users/{user_id}/grants", json={"projectId": project_id, "roleKeys": roles}
        ).raise_for_status()
        marker.touch()
        logger.info("Granted roles %s to %r", ", ".join(roles), admin_username)

    def new_client_secret(self, project_id: str, app_id: str) -> str:
        """Generate a fresh client secret for an existing app.

        Args:
            project_id: The project that owns the app.
            app_id: The OIDC app of the proxy.

        Returns:
            The new client secret.
        """
        response = self.client.post(
            f"{_API}/projects/{project_id}/apps/{app_id}/oidc_config/_generate_client_secret", json={}
        )
        response.raise_for_status()
        return response.json()["clientSecret"]

    def ensure_session_max_age(self) -> None:
        """Set the lifetime of refresh tokens on the instance, so a sign-in ends after ``session_max_age``.

        oauth2-proxy renews its session with the refresh token, so the session ends when Zitadel refuses to refresh.
        The other OIDC settings of the instance are kept.
        """
        current = self.client.get(f"{_ADMIN}/settings/oidc")
        current.raise_for_status()
        settings = current.json().get("settings") or {}
        wanted = f"{int(self.settings.session_max_age.total_seconds())}s"
        if settings.get("refreshTokenExpiration") == wanted:
            return
        kept = ("accessTokenLifetime", "idTokenLifetime", "refreshTokenIdleExpiration")
        body = {key: settings[key] for key in kept if key in settings}
        self.client.put(f"{_ADMIN}/settings/oidc", json={**body, "refreshTokenExpiration": wanted}).raise_for_status()
        logger.info("Set the refresh token lifetime to %s", wanted)

    def ensure_sign_in_lifetime(self) -> None:
        """Make the sign-in at Zitadel last ``session_max_age``, so a user enters credentials again when it ends.

        Without this, Zitadel keeps a password check valid for days and signs the user in again without credentials
        once the refresh token has expired. The other settings of the login policy of the instance are kept.
        """
        current = self.client.get(f"{_ADMIN}/policies/login")
        current.raise_for_status()
        policy = current.json().get("policy") or {}
        wanted = f"{int(self.settings.session_max_age.total_seconds())}s"
        if all(policy.get(key) == wanted for key in _CHECK_LIFETIMES):
            return
        body = {key: policy[key] for key in _LOGIN_POLICY if key in policy}
        self.client.put(
            f"{_ADMIN}/policies/login", json={**body, **dict.fromkeys(_CHECK_LIFETIMES, wanted)}
        ).raise_for_status()
        logger.info("Set the sign-in check lifetimes to %s", wanted)

    def run(self) -> None:
        """Provision the OIDC app and write the oauth2-proxy config."""
        settings = self.settings
        project_id = self.ensure_project()
        settings.project_id_file.write_text(project_id, encoding="utf-8")
        app_id, client_id, client_secret = self.ensure_app(project_id)
        self.sync_app_config(project_id, app_id)
        self.ensure_session_max_age()
        self.ensure_sign_in_lifetime()
        self.assert_project_roles(project_id)
        new_roles = self.ensure_roles(project_id)
        self.ensure_groups_executions(self.ensure_groups_target())
        self.grant_admin_roles(project_id, new_roles)

        existing = read_proxy_config(settings.proxy_config_file)
        cookie_secret = existing.get("cookie_secret") or secrets.token_hex(16)
        if client_secret is None:
            if existing.get("client_id") == client_id and existing.get("client_secret"):
                client_secret = existing["client_secret"]
            else:
                client_secret = self.new_client_secret(project_id, app_id)
                logger.info("Generated a new client secret for %r", settings.app_name)

        if write_proxy_config(settings.proxy_config_file, client_id, client_secret, cookie_secret):
            logger.info("Wrote %s", settings.proxy_config_file)


def main() -> int:
    """Run the bootstrap as the entry point of the ``pluginlake-init`` container.

    Returns:
        The process exit code.
    """
    setup_logging()
    settings = BootstrapSettings()
    token = wait_for_file(settings.admin_pat_file, settings.wait_seconds)
    headers = {"Authorization": f"Bearer {token}", "Host": settings.auth_host}
    with httpx.Client(base_url=settings.zitadel_url, headers=headers, timeout=30) as client:
        provisioner = ZitadelBootstrap(client, settings)
        provisioner.wait_until_ready()
        provisioner.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
