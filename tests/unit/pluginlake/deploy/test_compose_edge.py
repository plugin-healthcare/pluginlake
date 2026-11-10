"""Consistency tests for the production edge stack (Traefik, oauth2-proxy, Zitadel)."""

import re
from pathlib import Path

import yaml

from pluginlake.deploy.bootstrap import read_proxy_config, redirect_uris, write_proxy_config
from pluginlake.deploy.config_bootstrap import BootstrapSettings

COMPOSE_DIR = Path(__file__).resolve().parents[4] / "deploy" / "compose"
PUBLIC_ROUTERS = {"zitadel", "zitadel-login", "zitadel-root", "oauth2-proxy"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _services() -> dict:
    return _load(COMPOSE_DIR / "docker-compose.yaml")["services"]


def test_only_traefik_publishes_ports():
    published = {name for name, service in _services().items() if service.get("ports")}
    assert published == {"traefik"}


def test_no_service_mounts_the_docker_socket():
    for name, service in _services().items():
        volumes = [str(v) for v in service.get("volumes", [])]
        assert not any("docker.sock" in v for v in volumes if name != "cadvisor"), name


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
            assert "sso-auth" in router["middlewares"], name


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
