"""Supply-chain and hardening rules for the compose files and Dockerfiles (docs/guides/security.md)."""

import re
from pathlib import Path

import pytest
import yaml

from pluginlake.deploy.images import IMAGE_NAMES, PROD_COMPOSE_FILE, image_env_var

REPO = Path(__file__).resolve().parents[4]
COMPOSE_FILES = sorted([*(REPO / "deploy" / "compose").glob("docker-compose*.yaml"), PROD_COMPOSE_FILE])
DOCKERFILES = sorted((REPO / "deploy" / "docker").glob("*Dockerfile"))

_PINNED = re.compile(r"^[^\s@]+:[^\s@:]+@sha256:[0-9a-f]{64}$")
# Our own images in the production stack, filled from the images lock by `pluginlake up`.
_LOCK_VARIABLE = re.compile(r"^\$\{(PLUGINLAKE_IMAGE_[A-Z_]+):\?[^}]*\}$")
_LOCK_VARIABLES = {image_env_var(name) for name in IMAGE_NAMES}

# cAdvisor reads the host's Docker state, which needs root and its default capabilities.
_HARDENING_EXCEPTIONS = {"cadvisor": {"user", "cap_drop"}}
_ROOT_USERS = {"0", "root"}
# Services allowed to publish a port on all interfaces; everything else is loopback or internal.
_PUBLIC_SERVICES = {"pluginlake"}
_NOT_PUBLISHED = {"postgres", "marquez-db", "marquez", "dagster-code-server", "postgres-exporter", "cadvisor"}


def _services(path: Path) -> dict[str, dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")).get("services", {})


def _prod_services() -> dict[str, dict]:
    return _services(PROD_COMPOSE_FILE)


def image_is_pinned(image: str, *, allow_lock_variable: bool = False) -> bool:
    """Whether a compose ``image`` is pinned by digest (or is an images-lock variable)."""
    if _PINNED.match(image):
        return True
    match = _LOCK_VARIABLE.match(image)
    return allow_lock_variable and match is not None and match.group(1) in _LOCK_VARIABLES


@pytest.mark.parametrize(
    ("image", "pinned"),
    [
        ("dhi.io/postgres:17-alpine3.24@sha256:" + "a" * 64, True),
        ("dhi.io/postgres:17-alpine3.24", False),
        ("marquezproject/marquez:latest", False),
        ("postgres@sha256:" + "a" * 64, False),  # a tag is required for readability and Dependabot
        ("${PLUGINLAKE_IMAGE_API:?set by pluginlake up}", True),
        ("${PLUGINLAKE_IMAGE_API:-ghcr.io/plugin-healthcare/pluginlake/api:latest}", False),
        ("${PLUGINLAKE_IMAGE_OTHER:?x}", False),
    ],
)
def test_image_is_pinned_rejects_tag_only(image: str, pinned: bool):
    assert image_is_pinned(image, allow_lock_variable=True) is pinned


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.name)
def test_compose_images_pinned_by_digest(compose_file: Path):
    allow_variable = compose_file == PROD_COMPOSE_FILE
    unpinned = {
        name: service["image"]
        for name, service in _services(compose_file).items()
        if "image" in service and not image_is_pinned(service["image"], allow_lock_variable=allow_variable)
    }
    assert not unpinned, f"images without digest in {compose_file.name}: {unpinned}"


def test_prod_compose_uses_every_lock_variable():
    images = {service["image"] for service in _prod_services().values()}
    used = {m.group(1) for image in images if (m := _LOCK_VARIABLE.match(image))}
    assert used == _LOCK_VARIABLES - {image_env_var("ui-central")}


def test_prod_compose_has_no_build_sections():
    assert not [name for name, service in _prod_services().items() if "build" in service]


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda p: p.name)
def test_dockerfile_base_images_pinned_by_digest(dockerfile: Path):
    text = dockerfile.read_text(encoding="utf-8")
    refs = re.findall(r"^FROM\s+(\S+)", text, re.MULTILINE) + re.findall(r"COPY\s+--from=(\S+\.\S+)", text)
    assert refs
    assert all(_PINNED.match(ref) for ref in refs), refs
    assert re.match(r"# syntax=docker/dockerfile:1@sha256:[0-9a-f]{64}\n", text)


@pytest.mark.parametrize("name", sorted(_prod_services()))
def test_prod_service_is_hardened(name: str):
    service = _prod_services()[name]
    exceptions = _HARDENING_EXCEPTIONS.get(name, set())
    assert service.get("read_only") is True
    assert "no-new-privileges:true" in service.get("security_opt", [])
    if "cap_drop" not in exceptions:
        assert service.get("cap_drop") == ["ALL"]
        assert "cap_add" not in service
    if "user" not in exceptions:
        user = str(service.get("user", ""))
        assert user, f"{name} must set a non-root user"
        assert user.split(":", maxsplit=1)[0] not in _ROOT_USERS
    assert "privileged" not in service


def test_prod_hardening_is_a_shared_block():
    text = PROD_COMPOSE_FILE.read_text(encoding="utf-8")
    hardened = {name for name in _prod_services() if name not in _HARDENING_EXCEPTIONS}
    assert "x-hardening: &hardening" in text
    assert text.count("<<: *hardening") == len(hardened)


def _published(service: dict) -> list[str]:
    return [str(port) for port in service.get("ports", [])]


@pytest.mark.parametrize("name", sorted(_prod_services()))
def test_prod_only_api_published_on_all_interfaces(name: str):
    ports = _published(_prod_services()[name])
    if name in _NOT_PUBLISHED:
        assert not ports
    elif name not in _PUBLIC_SERVICES:
        assert all(port.startswith("127.0.0.1:") for port in ports), ports
