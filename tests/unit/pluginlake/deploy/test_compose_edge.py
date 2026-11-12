"""Consistency tests for the production edge stack (Traefik, oauth2-proxy, Zitadel)."""

import json
import re
from pathlib import Path

import httpx
import yaml

from pluginlake.api.config import HubSettings
from pluginlake.deploy.bootstrap import (
    ensure_groups_executions,
    ensure_groups_target,
    ensure_roles,
    read_proxy_config,
    redirect_uris,
    write_proxy_config,
)
from pluginlake.deploy.config import NodeSettings, StationConfig, load_init_config
from pluginlake.deploy.config_bootstrap import BootstrapSettings
from pluginlake.deploy.setup import compose_env

COMPOSE_DIR = Path(__file__).resolve().parents[4] / "deploy" / "compose"
PUBLIC_ROUTERS = {"zitadel", "zitadel-login", "zitadel-root", "oauth2-proxy"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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


def test_only_traefik_publishes_ports():
    published = {name for name, service in _services().items() if service.get("ports")}
    assert published == {"traefik"}


def test_no_service_mounts_the_docker_socket():
    for name, service in _services().items():
        volumes = [str(v) for v in service.get("volumes", [])]
        assert not any("docker.sock" in v for v in volumes if name != "cadvisor"), name


def test_every_required_compose_variable_is_written_by_setup():
    text = (COMPOSE_DIR / "docker-compose.yaml").read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{([A-Z_0-9]+):?\?", text))
    written = {
        line.split("=")[0]
        for line in compose_env(
            NodeSettings(domain="x.nl"), StationConfig(), owner=(1, 1), host_home=Path("/h")
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
    routers = _load(COMPOSE_DIR / "traefik" / "dynamic" / "routes.yaml")["http"]["routers"]
    for name, router in routers.items():
        if name not in PUBLIC_ROUTERS:
            assert any(m.startswith("sso-auth") for m in router["middlewares"]), name


def test_every_protected_host_has_a_router():
    routers = _load(COMPOSE_DIR / "traefik" / "dynamic" / "routes.yaml")["http"]["routers"]
    for subdomain in BootstrapSettings().protected_subdomains:
        assert f"Host(`{subdomain}." in routers[subdomain]["rule"], subdomain


def test_redirect_uris_cover_each_host():
    assert redirect_uris(["api.example.org"]) == ["https://api.example.org/oauth2/callback"]


def test_proxy_config_round_trip(tmp_path: Path):
    path = tmp_path / "oauth2-proxy.cfg"
    write_proxy_config(path, "client", 'se"cret', "cookie")
    assert read_proxy_config(path) == {"client_id": "client", "client_secret": 'se"cret', "cookie_secret": "cookie"}


def test_hub_is_served_on_the_bare_domain_behind_forward_auth():
    routers = _load(COMPOSE_DIR / "traefik" / "dynamic" / "routes.yaml")["http"]["routers"]
    assert routers["hub"]["rule"] == 'Host(`{{ env "PLUGINLAKE_DOMAIN" }}`)'
    assert "sso-auth" in routers["hub"]["middlewares"]
    assert BootstrapSettings(domain="example.org").protected_hosts[0] == "example.org"


def test_each_application_requires_the_role_with_its_own_name():
    http = _load(COMPOSE_DIR / "traefik" / "dynamic" / "routes.yaml")["http"]
    for app in BootstrapSettings().protected_subdomains:
        assert f"sso-auth-{app}" in http["routers"][app]["middlewares"], app
        assert http["middlewares"][f"sso-auth-{app}"]["forwardAuth"]["address"].endswith(f"?allowed_groups={app}"), app


def test_hub_lists_exactly_the_protected_applications():
    assert set(HubSettings().apps) == set(BootstrapSettings().protected_subdomains)


def _recording_client(responses: dict[str, dict]) -> tuple[httpx.Client, list[tuple[str, str, dict]]]:
    calls: list[tuple[str, str, dict]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        return httpx.Response(200, json=responses.get(f"{request.method} {request.url.path}", {}))

    return httpx.Client(base_url="http://zitadel", transport=httpx.MockTransport(handle)), calls


def test_ensure_roles_only_creates_missing_roles():
    client, calls = _recording_client({"POST /management/v1/projects/p/roles/_search": {"result": [{"key": "api"}]}})
    ensure_roles(client, "p", ["api", "dagster"])
    created = [body["roleKey"] for method, path, body in calls if path.endswith("/roles")]
    assert created == ["dagster"]


def test_groups_target_is_fail_closed_and_stores_key(tmp_path):
    client, calls = _recording_client(
        {
            "POST /v2/actions/targets/search": {},
            "POST /v2/actions/targets": {"id": "t1", "signingKey": "secret"},
        }
    )
    key_file = tmp_path / "hook.key"
    assert ensure_groups_target(client, "http://hook/groups", key_file) == "t1"
    created = next(body for method, path, body in calls if path == "/v2/actions/targets")
    assert created["restCall"] == {"interruptOnError": True}
    assert key_file.read_text().strip() == "secret"


def test_groups_target_reuses_existing_and_restores_missing_key(tmp_path):
    existing = {"id": "t1", "endpoint": "http://hook/groups", "signingKey": "secret"}
    client, calls = _recording_client({"POST /v2/actions/targets/search": {"targets": [existing]}})
    key_file = tmp_path / "hook.key"
    assert ensure_groups_target(client, "http://hook/groups", key_file) == "t1"
    assert [method for method, _, _ in calls] == ["POST"]
    assert key_file.read_text().strip() == "secret"


def test_groups_executions_cover_both_token_functions():
    client, calls = _recording_client({})
    ensure_groups_executions(client, "t1")
    functions = [body["condition"]["function"]["name"] for _, _, body in calls]
    assert functions == ["preuserinfo", "preaccesstoken"]
