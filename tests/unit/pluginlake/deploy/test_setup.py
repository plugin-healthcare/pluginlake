"""Tests for ``pluginlake setup``."""

import stat
from pathlib import Path

import pytest

from pluginlake.deploy.config import MonitoringSettings, NodeSettings, StationConfig, StationSettings
from pluginlake.deploy.setup import compose_env, resolve_node, run_setup


def _config(tmp_path: Path, node: str = "") -> Path:
    path = tmp_path / "pluginlake.toml"
    path.write_text(f"[node]\n{node}", encoding="utf-8")
    return path


def test_a_domain_is_required_outside_development():
    with pytest.raises(ValueError, match="domain"):
        resolve_node(NodeSettings(), dev=False)


def test_development_defaults_to_localhost():
    assert resolve_node(NodeSettings(), dev=True).domain == "pluginlake.localhost"


def test_a_configured_domain_wins_in_development():
    assert resolve_node(NodeSettings(domain="lake.test"), dev=True).domain == "lake.test"


def test_compose_env_holds_the_values_compose_needs():
    config = StationConfig(
        station=StationSettings(lineage_namespace="ds-1"), monitoring=MonitoringSettings(station_id="ds-1")
    )
    env = compose_env(NodeSettings(domain="lake.nl"), config, owner=(1000, 1001), host_home=Path("/srv/lake"))
    assert env.splitlines() == [
        "PLUGINLAKE_UID='1000'",
        "PLUGINLAKE_GID='1001'",
        "PLUGINLAKE_HOME='/srv/lake'",
        "PLUGINLAKE_DOMAIN='lake.nl'",
        "OAUTH2_PROXY_SSL_CERT_FILE=''",
        "ZITADEL_ADMIN_USERNAME='admin'",
        "PLUGINLAKE_LINEAGE_NAMESPACE='ds-1'",
        "PROMETHEUS_STATION_ID='ds-1'",
        "PROMETHEUS_SCRAPE_CADVISOR='true'",
        "PROMETHEUS_REMOTE_WRITE_URL=''",
    ]


def _write_mkcert_files(home: Path) -> None:
    (home / "tls").mkdir(parents=True)
    for name in ("cert.pem", "key.pem", "ca.pem"):
        (home / "tls" / name).write_text("pem")


def test_dev_setup_serves_the_mkcert_certificate_and_trusts_its_ca(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    _write_mkcert_files(home)
    assert run_setup(_config(tmp_path), home, dev=True) == 0
    assert "certFile: /tls/cert.pem" in (home / "tls" / "tls.yaml").read_text()
    assert "OAUTH2_PROXY_SSL_CERT_FILE='/tls/ca.pem'" in (home / "compose.env").read_text()


def test_dev_setup_without_a_certificate_fails(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_setup(_config(tmp_path), home, dev=True) == 1


def test_setup_keeps_the_own_certificate_config_of_the_operator(tmp_path: Path):
    home = tmp_path / "home"
    (home / "tls").mkdir(parents=True)
    (home / "tls" / "tls.yaml").write_text("tls: {own: true}\n")
    assert run_setup(_config(tmp_path, 'domain = "lake.nl"\n'), home) == 0
    assert (home / "tls" / "tls.yaml").read_text() == "tls: {own: true}\n"


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
    _write_mkcert_files(home)
    assert run_setup(_config(tmp_path), home, dev=True) == 0
    env = (home / "secrets.env").read_text()
    password = (home / "secrets" / "postgres_password").read_text()
    assert f"POSTGRES_PASSWORD='{password}'" in env
    assert "ZITADEL_CONFIG.YAML" not in env
    assert stat.S_IMODE((home / "secrets.env").stat().st_mode) == 0o600
