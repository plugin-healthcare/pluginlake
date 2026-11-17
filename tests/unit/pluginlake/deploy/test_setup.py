"""Tests for ``pluginlake setup``."""

import stat
from pathlib import Path

import pytest

from pluginlake.deploy.config import MonitoringSettings, NodeSettings, StationConfig, StationSettings
from pluginlake.deploy.setup import compose_env, is_local, require_domain, run_setup


def _config(tmp_path: Path, node: str = "") -> Path:
    path = tmp_path / "pluginlake.toml"
    path.write_text(f"[node]\n{node}", encoding="utf-8")
    return path


def test_a_domain_is_required():
    with pytest.raises(ValueError, match="domain"):
        require_domain(NodeSettings())


def test_only_domains_below_localhost_are_local():
    assert is_local("pluginlake.localhost")
    assert is_local("localhost")
    assert not is_local("lake.nl")
    assert not is_local("notlocalhost.nl")


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
        "COMPOSE_PROFILES='cadvisor'",
        "PROMETHEUS_REMOTE_WRITE_URL=''",
        "PROMETHEUS_REMOTE_WRITE_USERNAME=''",
        "PROMETHEUS_RETENTION='15d'",
    ]


def test_disabled_cadvisor_is_not_started():
    config = StationConfig(monitoring=MonitoringSettings(cadvisor=False))
    env = compose_env(NodeSettings(domain="lake.nl"), config, owner=(1, 1), host_home=Path("/h"))
    assert "COMPOSE_PROFILES=''" in env.splitlines()


def _write_mkcert_files(home: Path) -> None:
    (home / "tls").mkdir(parents=True)
    for name in ("cert.pem", "key.pem", "ca.pem"):
        (home / "tls" / name).write_text("pem")


def test_local_setup_serves_the_mkcert_certificate_and_trusts_its_ca(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    _write_mkcert_files(home)
    assert run_setup(_config(tmp_path, 'domain = "pluginlake.localhost"\n'), home) == 0
    assert "certFile: /tls/cert.pem" in (home / "tls" / "tls.yaml").read_text()
    assert "OAUTH2_PROXY_SSL_CERT_FILE='/tls/ca.pem'" in (home / "compose.env").read_text()


def test_local_setup_without_a_certificate_fails(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_setup(_config(tmp_path, 'domain = "pluginlake.localhost"\n'), home) == 1


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
