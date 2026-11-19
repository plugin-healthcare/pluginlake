"""Consistency tests for the production edge stack (Traefik, oauth2-proxy, Zitadel)."""

import json
import re
from pathlib import Path

import httpx
import pytest
import yaml

from pluginlake.deploy.bootstrap import (
    ZitadelBootstrap,
    read_proxy_config,
    redirect_uris,
    write_proxy_config,
)
from pluginlake.deploy.config import NodeSettings, StationConfig, load_init_config
from pluginlake.deploy.config_bootstrap import BootstrapSettings
from pluginlake.deploy.routes import APPLICATIONS, COOKIE_APPLICATIONS, render_routes
from pluginlake.deploy.setup import compose_env

COMPOSE_DIR = Path(__file__).resolve().parents[4] / "deploy" / "compose"
PUBLIC_ROUTERS = {"zitadel", "zitadel-login", "zitadel-root", "oauth2-proxy", "root"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _routes(domain: str = "lake.test") -> dict:
    return yaml.safe_load(render_routes(domain))["http"]


def _services() -> dict:
    return _load(COMPOSE_DIR / "docker-compose.yaml")["services"]


def test_every_compose_secret_is_generated():
    compose = _load(COMPOSE_DIR / "docker-compose.yaml")["secrets"]
    assert set(compose) <= {spec.name for spec in load_init_config().secrets}


def test_secrets_are_mounted_by_the_services_that_secrets_toml_lists():
    mounted: dict[str, set[str]] = {}
    for name, service in _services().items():
        for secret in service.get("secrets", []):
            mounted.setdefault(secret if isinstance(secret, str) else secret["source"], set()).add(name)
    declared = {spec.name: set(spec.services) for spec in load_init_config().secrets}
    assert {name: mounted.get(name, set()) for name in declared} == declared


def test_every_service_drops_all_capabilities():
    for name, service in _services().items():
        assert "no-new-privileges:true" in service.get("security_opt", []), name
        assert service.get("cap_drop") == ["ALL"], name
        assert service.get("read_only") is True, name


def test_marquez_uses_the_main_postgres_with_its_own_role():
    services = _services()
    assert "marquez-db" not in services
    assert services["marquez"]["environment"]["POSTGRES_HOST"] == "postgres"
    assert any(str(arg).startswith("--role=marquez:marquez:") for arg in services["pluginlake-db-init"]["command"])


def test_bootstrap_folders_are_mounted_per_consumer():
    services = _services()
    for name, service in services.items():
        for volume in service.get("volumes", []):
            assert not str(volume).split(":")[0].endswith("/bootstrap"), name
    assert not any(":/tls" in str(v) for v in services["oauth2-proxy"]["volumes"])


def test_only_traefik_publishes_ports():
    published = {name for name, service in _services().items() if service.get("ports")}
    assert published == {"traefik", "prometheus"}  # prometheus is bound to a host address, loopback by default


@pytest.mark.parametrize("compose_file", ["docker-compose.yaml", "docker-compose.dev.yaml"])
def test_only_the_socket_proxy_reaches_the_docker_socket(compose_file: str):
    services = _load(COMPOSE_DIR / compose_file)["services"]
    with_socket = {
        name
        for name, service in services.items()
        if any(
            str(v).startswith(("/var/run/docker.sock:", "/var/run:", "/run:", "/:")) for v in service.get("volumes", [])
        )
    }
    assert with_socket == {"docker-socket-proxy"}
    proxy = services["docker-socket-proxy"]
    assert proxy["networks"] == ["docker-api"]
    assert not any(arg.startswith(("-allowPOST", "-allowPUT", "-allowDELETE")) for arg in proxy["command"])


def test_every_required_compose_variable_is_written_by_setup():
    text = (COMPOSE_DIR / "docker-compose.yaml").read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{([A-Z_0-9]+):?\?", text))
    written = {
        line.split("=")[0]
        for line in compose_env(
            NodeSettings(domain="x.nl"), StationConfig(), owner=(1, 1), host_home=Path("/h"), secrets_revision="r1"
        ).splitlines()
    }
    assert required <= written


def test_compose_has_no_defaults_and_no_named_volumes():
    text = (COMPOSE_DIR / "docker-compose.yaml").read_text(encoding="utf-8")
    assert not re.search(r"\$\{[A-Z_0-9]+:-", text)
    assert "\nvolumes:" not in text


def test_services_that_read_secret_files_run_as_the_host_user():
    services = _services()
    readers = [name for name, service in services.items() if service.get("secrets") and name != "postgres"]
    missing = [name for name in readers if "PLUGINLAKE_UID" not in str(services[name].get("user", ""))]
    assert missing == []


def test_zitadel_does_not_allow_self_registration():
    env = _services()["zitadel-api"]["environment"]
    assert env["ZITADEL_DEFAULTINSTANCE_LOGINPOLICY_ALLOWREGISTER"] == "false"


def test_zitadel_services_have_no_env_file():
    services = _services()
    assert [name for name in ("zitadel-init", "zitadel-api", "zitadel-login") if "env_file" in services[name]] == []


def test_no_env_file_reads_from_the_secrets_folder():
    services = _services()
    paths = [str(item) for service in services.values() for item in _as_list(service.get("env_file", []))]
    assert [path for path in paths if "/secrets/" in path] == []


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else [value]


def test_no_secret_is_read_from_the_environment():
    secrets = _load(COMPOSE_DIR / "docker-compose.yaml")["secrets"]
    assert all("file" in secret for secret in secrets.values())


def test_database_network_is_internal():
    assert _load(COMPOSE_DIR / "docker-compose.yaml")["networks"]["db-net"]["internal"] is True


def test_edge_images_are_pinned_by_digest():
    services = _services()
    for name in ("traefik", "zitadel-api", "zitadel-login", "oauth2-proxy"):
        assert "@sha256:" in services[name]["image"], name


def test_every_application_router_is_behind_forward_auth():
    routers = _routes()["routers"]
    for name, router in routers.items():
        if name not in PUBLIC_ROUTERS:
            assert any(m.startswith("sso-auth") for m in router["middlewares"]), name


def test_applications_without_own_cookies_never_receive_the_session_cookie():
    http = _routes()
    assert http["middlewares"]["drop-cookies"]["headers"]["customRequestHeaders"] == {"Cookie": ""}
    for app in APPLICATIONS:
        middlewares = http["routers"][app]["middlewares"]
        if app in COOKIE_APPLICATIONS:
            assert "drop-cookies" not in middlewares, app
        else:
            assert middlewares.index("drop-cookies") > middlewares.index(f"sso-auth-{app}"), app


def test_every_protected_host_has_a_router():
    routers = _routes()["routers"]
    for subdomain in BootstrapSettings().protected_subdomains:
        assert f"Host(`{subdomain}." in routers[subdomain]["rule"], subdomain


def test_the_routed_applications_are_the_protected_subdomains():
    assert set(APPLICATIONS) == set(BootstrapSettings().protected_subdomains)


def test_routes_use_the_node_domain_for_every_host():
    assert "{{" not in render_routes("lake.test")
    assert "pluginlake.localhost" not in render_routes("lake.test")


def test_redirect_uris_cover_each_host():
    assert redirect_uris(["api.example.org"]) == ["https://api.example.org/oauth2/callback"]


def test_proxy_config_round_trip(tmp_path: Path):
    path = tmp_path / "oauth2-proxy.cfg"
    write_proxy_config(path, "client", 'se"cret', "cookie")
    assert read_proxy_config(path) == {"client_id": "client", "client_secret": 'se"cret', "cookie_secret": "cookie"}


def test_unchanged_proxy_config_is_not_rewritten(tmp_path: Path):
    path = tmp_path / "oauth2-proxy.cfg"
    assert write_proxy_config(path, "client", "secret", "cookie") is True
    assert write_proxy_config(path, "client", "secret", "cookie") is False
    assert write_proxy_config(path, "client", "other", "cookie") is True
    assert [p.name for p in tmp_path.iterdir()] == ["oauth2-proxy.cfg"]


def test_bare_domain_redirects_to_the_console():
    http = _routes()
    assert http["routers"]["root"]["rule"] == "Host(`lake.test`)"
    assert http["middlewares"]["root-redirect"]["redirectRegex"]["replacement"] == "https://console.lake.test/"
    assert BootstrapSettings(domain="example.org").protected_hosts[0] == "example.org"


def test_traefik_drops_headers_that_alias_the_identity_headers():
    static = _load(COMPOSE_DIR / "traefik" / "traefik.yaml")
    assert static["global"]["aliasHeadersStrategy"] == "delete"


def test_forward_auth_limits_the_response_body_size():
    middlewares = _routes()["middlewares"]
    for name, middleware in middlewares.items():
        if "forwardAuth" in middleware:
            assert middleware["forwardAuth"]["maxResponseBodySize"] > 0, name


def test_forward_auth_passes_the_refreshed_session_cookie():
    cookie_name = next(
        arg.split("=", 1)[1] for arg in _services()["oauth2-proxy"]["command"] if arg.startswith("--cookie-name=")
    )
    for name, middleware in _routes()["middlewares"].items():
        if "forwardAuth" in middleware:
            assert cookie_name in middleware["forwardAuth"]["addAuthCookiesToResponse"], name


def test_sign_in_returns_to_the_requested_page():
    assert _routes()["middlewares"]["sso-errors"]["errors"]["query"] == "/oauth2/sign_in?rd={url}"


def test_browser_applications_sign_out_a_user_without_the_role():
    http = _routes()
    assert http["middlewares"]["sso-forbidden"]["errors"]["statusRewrites"] == {"403": 302}
    for app in ("console", "dagster", "lineage", "prometheus"):
        assert "sso-forbidden" in http["routers"][app]["middlewares"], app


def test_browser_applications_show_the_starting_page_on_server_errors():
    http = _routes()
    assert http["middlewares"]["sso-starting"]["errors"]["service"] in http["services"]
    for app in ("console", "dagster", "lineage", "prometheus"):
        assert http["routers"][app]["middlewares"][0] == "sso-starting", app


def test_each_application_requires_its_existing_role():
    http = _routes()
    for app in BootstrapSettings().protected_subdomains:
        assert f"sso-auth-{app}" in http["routers"][app]["middlewares"], app
        role = "marquez" if app == "lineage" else app
        assert http["middlewares"][f"sso-auth-{app}"]["forwardAuth"]["address"].endswith(f"?allowed_groups={role}"), app


def _bootstrap(responses: dict[str, dict], **settings) -> tuple[ZitadelBootstrap, list[tuple[str, str, dict]]]:
    calls: list[tuple[str, str, dict]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        return httpx.Response(200, json=responses.get(f"{request.method} {request.url.path}", {}))

    client = httpx.Client(base_url="http://zitadel", transport=httpx.MockTransport(handle))
    return ZitadelBootstrap(client, BootstrapSettings(**settings)), calls


def test_ensure_roles_only_creates_missing_roles():
    bootstrap, calls = _bootstrap(
        {"POST /management/v1/projects/p/roles/_search": {"result": [{"key": "api"}]}},
        protected_subdomains=["api", "dagster"],
    )
    assert bootstrap.ensure_roles("p") == ["dagster"]
    created = [body["roleKey"] for method, path, body in calls if path.endswith("/roles")]
    assert created == ["dagster"]


def test_new_roles_are_added_to_the_existing_grant_of_the_admin(tmp_path):
    bootstrap, calls = _bootstrap(
        {
            "POST /management/v1/users/_search": {"result": [{"id": "u1", "human": {}}]},
            "POST /management/v1/users/grants/_search": {"result": [{"id": "g1", "roleKeys": ["api"]}]},
        },
        protected_subdomains=["api", "console"],
        admin_granted_file=tmp_path / "admin-granted",
    )
    bootstrap.grant_admin_roles("p", ["console"])
    update = next(body for method, path, body in calls if method == "PUT")
    assert update == {"roleKeys": ["api", "console"]}


def test_admin_keeps_a_removed_role_removed(tmp_path):
    bootstrap, calls = _bootstrap(
        {
            "POST /management/v1/users/_search": {"result": [{"id": "u1", "human": {}}]},
            "POST /management/v1/users/grants/_search": {"result": [{"id": "g1", "roleKeys": ["api"]}]},
        },
        protected_subdomains=["api", "dagster"],
        admin_granted_file=tmp_path / "admin-granted",
    )
    bootstrap.grant_admin_roles("p", [])
    assert not [
        call for call in calls if call[0] in {"PUT", "POST"} and "grants" in call[1] and "_search" not in call[1]
    ]


def test_first_admin_grant_is_created_once(tmp_path):
    marker = tmp_path / "admin-granted"
    responses = {
        "POST /management/v1/users/_search": {"result": [{"id": "u1", "human": {}}]},
        "POST /management/v1/users/grants/_search": {"result": []},
    }
    bootstrap, calls = _bootstrap(responses, protected_subdomains=["api"], admin_granted_file=marker)
    bootstrap.grant_admin_roles("p", ["api"])
    assert any(path == "/management/v1/users/u1/grants" for _, path, _ in calls)
    assert marker.exists()

    again, calls = _bootstrap(responses, protected_subdomains=["api"], admin_granted_file=marker)
    again.grant_admin_roles("p", [])
    assert not any(path == "/management/v1/users/u1/grants" for _, path, _ in calls)


def test_groups_target_is_fail_closed_and_stores_key(tmp_path):
    key_file = tmp_path / "hook.key"
    bootstrap, calls = _bootstrap(
        {
            "POST /v2/actions/targets/search": {},
            "POST /v2/actions/targets": {"id": "t1", "signingKey": "secret"},
        },
        groups_hook_url="http://hook/groups",
        groups_hook_key_file=key_file,
    )
    assert bootstrap.ensure_groups_target() == "t1"
    created = next(body for method, path, body in calls if path == "/v2/actions/targets")
    assert created["restCall"] == {"interruptOnError": True}
    assert key_file.read_text().strip() == "secret"


def test_groups_target_reuses_existing_and_restores_missing_key(tmp_path):
    existing = {"id": "t1", "endpoint": "http://hook/groups", "signingKey": "secret"}
    key_file = tmp_path / "hook.key"
    bootstrap, calls = _bootstrap(
        {"POST /v2/actions/targets/search": {"targets": [existing]}},
        groups_hook_url="http://hook/groups",
        groups_hook_key_file=key_file,
    )
    assert bootstrap.ensure_groups_target() == "t1"
    assert [method for method, _, _ in calls] == ["POST"]
    assert key_file.read_text().strip() == "secret"


def test_groups_executions_cover_both_token_functions():
    bootstrap, calls = _bootstrap({})
    bootstrap.ensure_groups_executions("t1")
    functions = [body["condition"]["function"]["name"] for method, _, body in calls if method == "PUT"]
    assert functions == ["preuserinfo", "preaccesstoken"]


def test_groups_executions_keep_the_targets_of_the_operator():
    existing = {"executions": [{"targets": ["other"]}]}
    bootstrap, calls = _bootstrap({"POST /v2/actions/executions/search": existing})
    bootstrap.ensure_groups_executions("t1")
    assert [body["targets"] for method, _, body in calls if method == "PUT"] == [["other", "t1"], ["other", "t1"]]


def test_groups_executions_are_left_alone_when_they_hold_the_target():
    bootstrap, calls = _bootstrap({"POST /v2/actions/executions/search": {"executions": [{"targets": ["t1"]}]}})
    bootstrap.ensure_groups_executions("t1")
    assert not [call for call in calls if call[0] == "PUT"]


def test_groups_target_endpoint_is_updated_with_post(tmp_path):
    existing = {"id": "t1", "endpoint": "http://old/groups", "signingKey": "secret"}
    bootstrap, calls = _bootstrap(
        {"POST /v2/actions/targets/search": {"targets": [existing]}},
        groups_hook_url="http://hook/groups",
        groups_hook_key_file=tmp_path / "hook.key",
    )
    bootstrap.ensure_groups_target()
    assert ("POST", "/v2/actions/targets/t1", {"endpoint": "http://hook/groups"}) in calls


def test_new_app_may_refresh_its_tokens():
    bootstrap, calls = _bootstrap(
        {"POST /management/v1/projects/p/apps/oidc": {"appId": "a", "clientId": "c", "clientSecret": "s"}}
    )
    bootstrap.ensure_app("p")
    created = next(body for _, path, body in calls if path.endswith("/apps/oidc"))
    assert "OIDC_GRANT_TYPE_REFRESH_TOKEN" in created["grantTypes"]


def test_existing_app_gets_the_refresh_grant_and_keeps_its_settings():
    app = {
        "redirectUris": [],
        "additionalOrigins": ["https://other.example"],
        "allowedOrigins": ["https://other.example"],
        "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
        "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"],
        "postLogoutRedirectUris": ["https://console.lake.test/"],
        "accessTokenType": "OIDC_TOKEN_TYPE_JWT",
        "clockSkew": "2s",
    }
    bootstrap, calls = _bootstrap({"GET /management/v1/projects/p/apps/a": {"app": {"oidcConfig": app}}})
    bootstrap.sync_app_config("p", "a")
    updated = next(body for method, _, body in calls if method == "PUT")
    assert updated["grantTypes"] == ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE", "OIDC_GRANT_TYPE_REFRESH_TOKEN"]
    assert updated["postLogoutRedirectUris"] == ["https://console.lake.test/"]
    assert updated["accessTokenType"] == "OIDC_TOKEN_TYPE_JWT"
    assert updated["clockSkew"] == "2s"
    assert "https://other.example" in updated["additionalOrigins"]
    assert "allowedOrigins" not in updated


def test_sign_in_lasts_at_most_the_session_max_age():
    current = {"settings": {"accessTokenLifetime": "43200s", "refreshTokenExpiration": "7776000s"}}
    bootstrap, calls = _bootstrap({"GET /admin/v1/settings/oidc": current})
    bootstrap.ensure_session_max_age()
    assert (
        "PUT",
        "/admin/v1/settings/oidc",
        {"accessTokenLifetime": "43200s", "refreshTokenExpiration": "43200s"},
    ) in calls


def test_sign_in_at_zitadel_ends_with_the_session_and_keeps_the_login_policy():
    current = {
        "policy": {"allowRegister": False, "forceMfa": True, "passwordCheckLifetime": "864000s", "isDefault": True}
    }
    bootstrap, calls = _bootstrap({"GET /admin/v1/policies/login": current})
    bootstrap.ensure_sign_in_lifetime()
    method, path, body = calls[-1]
    assert (method, path) == ("PUT", "/admin/v1/policies/login")
    assert body == {
        "allowRegister": False,
        "forceMfa": True,
        "passwordCheckLifetime": "43200s",
        "externalLoginCheckLifetime": "43200s",
        "secondFactorCheckLifetime": "43200s",
        "multiFactorCheckLifetime": "43200s",
    }


def test_aligned_sign_in_lifetime_is_left_alone():
    policy = dict.fromkeys(
        [
            "passwordCheckLifetime",
            "externalLoginCheckLifetime",
            "secondFactorCheckLifetime",
            "multiFactorCheckLifetime",
        ],
        "43200s",
    )
    bootstrap, calls = _bootstrap({"GET /admin/v1/policies/login": {"policy": policy}})
    bootstrap.ensure_sign_in_lifetime()
    assert [method for method, _, _ in calls] == ["GET"]


def test_session_max_age_is_left_alone_when_it_is_set():
    bootstrap, calls = _bootstrap({"GET /admin/v1/settings/oidc": {"settings": {"refreshTokenExpiration": "43200s"}}})
    bootstrap.ensure_session_max_age()
    assert [method for method, _, _ in calls] == ["GET"]
