"""Consistency tests for the monitoring deploy config (``deploy/monitoring``, compose profile)."""

from pathlib import Path

import pytest
import yaml

from pluginlake.api.config import MetricsSettings

DEPLOY_DIR = Path(__file__).resolve().parents[4] / "deploy"
PROMETHEUS_DIR = DEPLOY_DIR / "monitoring" / "prometheus"
COMPOSE_FILES = ["docker-compose.dev.yaml", "docker-compose.yaml"]
MONITORING_SERVICES = {"prometheus", "postgres-exporter", "cadvisor"}


def _compose(name: str) -> dict:
    return yaml.safe_load((DEPLOY_DIR / "compose" / name).read_text(encoding="utf-8"))


def _scrape_targets() -> dict[str, list[str]]:
    targets: dict[str, list[str]] = {}
    for path in sorted((PROMETHEUS_DIR / "scrape.d").glob("*.yml")):
        for job in yaml.safe_load(path.read_text(encoding="utf-8"))["scrape_configs"]:
            targets[job["job_name"]] = [t for sc in job["static_configs"] for t in sc["targets"]]
    return targets


def test_prometheus_config_loads_scrape_files():
    config = yaml.safe_load((PROMETHEUS_DIR / "prometheus.yml").read_text(encoding="utf-8"))
    assert config["scrape_config_files"] == ["scrape.d/*.yml"]
    assert config["global"]["external_labels"] == {"station": "${PROMETHEUS_STATION_ID}"}


def test_scrape_jobs():
    assert set(_scrape_targets()) == {"prometheus", "pluginlake", "postgres", "cadvisor"}


def test_pluginlake_target_matches_metrics_port():
    assert _scrape_targets()["pluginlake"] == [f"pluginlake:{MetricsSettings().port}"]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_scrape_targets_exist_as_services(compose_file: str):
    services = _compose(compose_file)["services"]
    for job, targets in _scrape_targets().items():
        for target in targets:
            host = target.split(":")[0]
            if host != "localhost":
                assert host in services, f"{job} target {host} missing in {compose_file}"


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_monitoring_services_use_profile(compose_file: str):
    services = _compose(compose_file)["services"]
    for name in MONITORING_SERVICES:
        assert services[name]["profiles"] == ["monitoring"]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_metrics_not_published(compose_file: str):
    services = _compose(compose_file)["services"]
    port = str(MetricsSettings().port)
    assert port in services["pluginlake"]["expose"]
    assert not any(port in str(p) for p in services["pluginlake"].get("ports", []))
    for name in MONITORING_SERVICES - {"prometheus"}:
        assert "ports" not in services[name]
    assert all(str(p).startswith("127.0.0.1:") for p in services["prometheus"].get("ports", []))


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_postgres_exporter_skips_table_level_collectors(compose_file: str):
    command = _compose(compose_file)["services"]["postgres-exporter"]["command"]
    assert "--no-collector.stat_user_tables" in command
    assert "--no-collector.statio_user_tables" in command


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_cadvisor_does_not_store_container_labels(compose_file: str):
    command = _compose(compose_file)["services"]["cadvisor"]["command"]
    assert "--store_container_labels=false" in command
