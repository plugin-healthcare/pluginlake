"""Tests for ``pluginlake setup``."""

import stat
from pathlib import Path

import pytest

from pluginlake.deploy.config import NodeSettings
from pluginlake.deploy.setup import compose_env, resolve_node, run_setup


def _config(tmp_path: Path, node: str = "") -> Path:
    path = tmp_path / "pluginlake.toml"
    path.write_text(f"[node]\n{node}", encoding="utf-8")
    return path


def test_a_domain_is_required_outside_development():
    with pytest.raises(ValueError, match="domain"):
        resolve_node(NodeSettings(), dev=False)


def test_development_defaults_to_localhost_with_insecure_tls():
    node = resolve_node(NodeSettings(), dev=True)
    assert (node.domain, node.insecure_tls) == ("pluginlake.localhost", True)


def test_a_configured_domain_wins_in_development():
    assert resolve_node(NodeSettings(domain="lake.test"), dev=True).domain == "lake.test"


def test_compose_env_holds_the_values_compose_needs():
    env = compose_env(NodeSettings(domain="lake.nl"), uid=1000, gid=1001, host_home=Path("/srv/lake"))
    assert env.splitlines() == [
        "PLUGINLAKE_UID='1000'",
        "PLUGINLAKE_GID='1001'",
        "PLUGINLAKE_HOME='/srv/lake'",
        "PLUGINLAKE_DOMAIN='lake.nl'",
        "OAUTH2_PROXY_INSECURE_TLS='false'",
        "ZITADEL_ADMIN_USERNAME='admin'",
    ]


def test_setup_writes_private_compose_env_and_secrets(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_setup(_config(tmp_path, 'domain = "lake.nl"\n'), home) == 0
    assert stat.S_IMODE((home / "compose.env").stat().st_mode) == 0o600
    assert "PLUGINLAKE_DOMAIN='lake.nl'" in (home / "compose.env").read_text()
    assert (home / "secrets" / "postgres_password").is_file()
    assert not (home / "secrets.env").exists()


def test_setup_without_domain_fails_and_creates_nothing(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_setup(_config(tmp_path), home) == 1
    assert list(home.iterdir()) == []


def test_dev_setup_writes_plain_secrets_to_a_private_env_file(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_setup(_config(tmp_path), home, dev=True) == 0
    env = (home / "secrets.env").read_text()
    password = (home / "secrets" / "postgres_password").read_text()
    assert f"POSTGRES_PASSWORD='{password}'" in env
    assert "ZITADEL_CONFIG.YAML" not in env
    assert stat.S_IMODE((home / "secrets.env").stat().st_mode) == 0o600
