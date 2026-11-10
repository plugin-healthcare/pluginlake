"""Tests for ``pluginlake up`` / ``pluginlake down`` and the lineage compose profile."""

import re
from pathlib import Path

import pytest
import yaml

from pluginlake.cli import up
from pluginlake.deploy.config import StationConfig, StationSettings

_COMPOSE_DIR = up._find_compose_dir()
_LINEAGE_SERVICES = ("marquez-db", "marquez", "marquez-web")


@pytest.fixture
def captured_cmd(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], cwd: Path) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr(up, "_run", fake_run)
    return calls


@pytest.fixture
def dev_compose() -> dict:
    assert _COMPOSE_DIR is not None
    return yaml.safe_load((_COMPOSE_DIR / "docker-compose.dev.yaml").read_text(encoding="utf-8"))


def _profiles_in(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--profile"]


def _write_config(tmp_path: Path, station: str) -> Path:
    path = tmp_path / "pluginlake.toml"
    path.write_text(f"[station]\n{station}\n", encoding="utf-8")
    return path


def test_compose_profiles_default_is_ui_only():
    assert up._compose_profiles(StationSettings()) == ["ui"]


def test_compose_profiles_with_lineage():
    settings = StationSettings(dashboards=False, lineage=True)
    assert up._compose_profiles(settings) == ["lineage"]


def test_run_up_enables_lineage_profile(tmp_path: Path, captured_cmd: list[list[str]]):
    config_path = _write_config(tmp_path, "lineage = true")
    assert up.run_up(config_path, detach=True, build=False) == 0
    assert _profiles_in(captured_cmd[0]) == ["ui", "lineage"]
    assert captured_cmd[0][-2:] == ["up", "-d"]


def test_run_up_without_lineage_omits_profile(tmp_path: Path, captured_cmd: list[list[str]]):
    config_path = _write_config(tmp_path, "lineage = false")
    assert up.run_up(config_path, build=False) == 0
    assert "lineage" not in _profiles_in(captured_cmd[0])


def test_run_up_invalid_config_returns_error(tmp_path: Path, captured_cmd: list[list[str]]):
    config_path = _write_config(tmp_path, 'lineage = "maybe"')
    assert up.run_up(config_path) == 1
    assert captured_cmd == []


def test_run_down_stops_all_profiles(captured_cmd: list[list[str]]):
    assert up.run_down(volumes=True) == 0
    assert _profiles_in(captured_cmd[0]) == ["ui", "lineage"]
    assert captured_cmd[0][-2:] == ["down", "-v"]


def test_override_sets_openlineage_env_on_dagster_when_enabled(tmp_path: Path):
    config = StationConfig(station=StationSettings(lineage=True, lineage_namespace="ds-test-001"))
    env = up._build_override(config, tmp_path / "pluginlake.toml")["services"]["dagster"]["environment"]
    assert env["OPENLINEAGE_URL"] == "http://marquez:5000"
    assert env["OPENLINEAGE_NAMESPACE"] == "ds-test-001"


def test_override_omits_openlineage_env_when_disabled(tmp_path: Path):
    override = up._build_override(StationConfig(), tmp_path / "pluginlake.toml")
    for service in override["services"].values():
        assert "OPENLINEAGE_URL" not in service["environment"]


def test_lineage_services_only_in_lineage_profile(dev_compose: dict):
    for name in _LINEAGE_SERVICES:
        assert dev_compose["services"][name]["profiles"] == ["lineage"]


def test_marquez_images_are_pinned(dev_compose: dict):
    for name in ("marquez", "marquez-web"):
        image = dev_compose["services"][name]["image"]
        repo, _, tag = image.partition(":")
        assert repo == f"marquezproject/{name}"
        assert re.fullmatch(r"\d+\.\d+\.\d+", tag)


def test_marquez_uses_dedicated_persistent_database(dev_compose: dict):
    services = dev_compose["services"]
    assert services["marquez"]["environment"]["POSTGRES_HOST"] == "marquez-db"
    volume_name, _, mount = services["marquez-db"]["volumes"][0].partition(":")
    assert volume_name in dev_compose["volumes"]
    assert volume_name not in str(services["postgres"]["volumes"])
    assert mount.startswith("/var/lib/postgresql/17/data")


def test_marquez_ui_bound_to_loopback_only(dev_compose: dict):
    services = dev_compose["services"]
    assert "ports" not in services["marquez"]
    assert "ports" not in services["marquez-db"]
    for port in services["marquez-web"]["ports"]:
        assert port.startswith("127.0.0.1:")
