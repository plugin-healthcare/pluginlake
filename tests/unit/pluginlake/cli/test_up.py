"""Tests for ``pluginlake up`` / ``pluginlake down``: compose profiles, lineage and monitoring."""

import json
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

    def fake_run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> int:
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
    assert up.run_up(config_path, detach=True, build=False, dev=True) == 0
    assert _profiles_in(captured_cmd[0]) == ["ui", "lineage"]
    assert captured_cmd[0][-2:] == ["up", "-d"]


def test_run_up_without_lineage_omits_profile(tmp_path: Path, captured_cmd: list[list[str]]):
    config_path = _write_config(tmp_path, "lineage = false")
    assert up.run_up(config_path, build=False, dev=True) == 0
    assert "lineage" not in _profiles_in(captured_cmd[0])


def test_run_up_invalid_config_returns_error(tmp_path: Path, captured_cmd: list[list[str]]):
    config_path = _write_config(tmp_path, 'lineage = "maybe"')
    assert up.run_up(config_path, dev=True) == 1
    assert captured_cmd == []


def test_run_down_stops_all_profiles(captured_cmd: list[list[str]]):
    assert up.run_down(volumes=True, dev=True) == 0
    assert _profiles_in(captured_cmd[0]) == ["ui", "lineage", "monitoring"]
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
        assert re.fullmatch(r"\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", tag)


def test_marquez_uses_dedicated_persistent_database(dev_compose: dict):
    services = dev_compose["services"]
    assert services["marquez"]["environment"]["POSTGRES_HOST"] == "marquez-db"
    volume_name, _, mount = services["marquez-db"]["volumes"][0].partition(":")
    assert volume_name in dev_compose["volumes"]
    assert volume_name not in str(services["postgres"]["volumes"])
    assert mount.startswith("/var/lib/postgresql/17/data")


def test_postgres_data_in_named_volume_at_pgdata(dev_compose: dict):
    volume_name, _, mount = dev_compose["services"]["postgres"]["volumes"][0].partition(":")
    assert volume_name in dev_compose["volumes"]
    assert mount == "/var/lib/postgresql/17/data"


def test_marquez_ui_bound_to_loopback_only(dev_compose: dict):
    services = dev_compose["services"]
    assert "ports" not in services["marquez"]
    assert "ports" not in services["marquez-db"]
    for port in services["marquez-web"]["ports"]:
        assert port.startswith("127.0.0.1:")


@pytest.fixture
def override_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture compose invocations (command and override contents) instead of running them."""
    captured: list[dict] = []

    def _fake_run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> int:
        files = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-f"]
        override = json.loads(Path(files[1]).read_text(encoding="utf-8")) if len(files) > 1 else None
        captured.append({"cmd": cmd, "override": override, "env": env})
        return 0

    monkeypatch.setattr(up, "_run", _fake_run)
    return captured


def _config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "pluginlake.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_up_without_monitoring(tmp_path: Path, override_calls: list[dict]):
    assert up.run_up(_config(tmp_path, "[station]\n"), dev=True) == 0
    cmd, override = override_calls[0]["cmd"], override_calls[0]["override"]
    assert "monitoring" not in _profiles_in(cmd)
    assert "prometheus" not in override["services"]


def test_up_with_monitoring(tmp_path: Path, override_calls: list[dict]):
    config = _config(tmp_path, '[monitoring]\nenabled = true\nstation_id = "ds-001"\n')
    assert up.run_up(config, detach=True, dev=True) == 0
    cmd, override = override_calls[0]["cmd"], override_calls[0]["override"]
    assert "monitoring" in _profiles_in(cmd)
    assert "--scale" not in cmd
    assert override["services"]["prometheus"]["environment"] == {
        "PROMETHEUS_STATION_ID": "ds-001",
        "PROMETHEUS_SCRAPE_CADVISOR": "true",
    }


def test_up_with_remote_write(tmp_path: Path, override_calls: list[dict]):
    url = "https://central.example.org/api/v1/write"
    config = _config(tmp_path, f'[monitoring]\nenabled = true\nremote_write_url = "{url}"\n')
    up.run_up(config, dev=True)
    env = override_calls[0]["override"]["services"]["prometheus"]["environment"]
    assert env["PROMETHEUS_REMOTE_WRITE_URL"] == url
    assert not any("PASSWORD" in key for key in env)


def test_up_without_cadvisor_scales_it_to_zero(tmp_path: Path, override_calls: list[dict]):
    config = _config(tmp_path, "[monitoring]\nenabled = true\ncadvisor = false\n")
    up.run_up(config, dev=True)
    cmd, override = override_calls[0]["cmd"], override_calls[0]["override"]
    assert cmd[cmd.index("--scale") + 1] == "cadvisor=0"
    assert cmd.index("--scale") > cmd.index("up")
    assert override["services"]["prometheus"]["environment"]["PROMETHEUS_SCRAPE_CADVISOR"] == "false"


def test_up_invalid_monitoring_config(tmp_path: Path, override_calls: list[dict], capsys: pytest.CaptureFixture[str]):
    config = _config(tmp_path, '[monitoring]\nremote_write_url = "not-a-url"\n')
    assert up.run_up(config, dev=True) == 1
    assert not override_calls
    assert "Invalid station config" in capsys.readouterr().err


def test_down_always_includes_monitoring(override_calls: list[dict]):
    assert up.run_down(dev=True) == 0
    cmd = override_calls[0]["cmd"]
    assert "monitoring" in _profiles_in(cmd)
    assert cmd[-1] == "down"


def test_compose_env_untouched_without_monitoring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(up.REMOTE_WRITE_SECRET_VAR, raising=False)
    assert up._compose_env(tmp_path, monitoring=False) is None


def test_compose_env_defaults_remote_write_password_to_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(up.REMOTE_WRITE_SECRET_VAR, raising=False)
    (tmp_path / ".env").write_text("POSTGRES_PASSWORD=x\n", encoding="utf-8")
    env = up._compose_env(tmp_path, monitoring=True)
    assert env is not None
    assert env[up.REMOTE_WRITE_SECRET_VAR] == ""


@pytest.mark.parametrize("line", ["PROMETHEUS_REMOTE_WRITE_PASSWORD=s3cret", "PROMETHEUS_REMOTE_WRITE_PASSWORD="])
def test_compose_env_keeps_password_from_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: str):
    monkeypatch.delenv(up.REMOTE_WRITE_SECRET_VAR, raising=False)
    (tmp_path / ".env").write_text(f"{line}\n", encoding="utf-8")
    assert up._compose_env(tmp_path, monitoring=True) is None


def test_compose_env_keeps_password_from_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(up.REMOTE_WRITE_SECRET_VAR, "s3cret")
    assert up._compose_env(tmp_path, monitoring=True) is None


# --- Production stack (default) ---

_IMAGE_ENV = {"PLUGINLAKE_IMAGE_API": "ghcr.io/plugin-healthcare/pluginlake/api:0.2.0@sha256:" + "a" * 64}
_BASE_SECRETS = ("postgres_password", "dagster_pg_password", "ducklake_pg_password")


@pytest.fixture
def station(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A station directory with .env.production, a secrets dir and a released images lock."""
    monkeypatch.setattr(up, "released_image_env", lambda: dict(_IMAGE_ENV))
    (tmp_path / ".env.production").write_text("POSTGRES_USER=dagster\n", encoding="utf-8")
    secrets = tmp_path / "secrets"
    secrets.mkdir(mode=0o700)
    for name in (*_BASE_SECRETS, "postgres_exporter_password", "marquez_db_password"):
        (secrets / name).write_text("pw", encoding="utf-8")
        (secrets / name).chmod(0o644)
    return tmp_path


@pytest.fixture
def prod_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    captured: list[dict] = []

    def _fake_run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> int:
        files = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-f"]
        override = json.loads(Path(files[1]).read_text(encoding="utf-8")) if len(files) > 1 else None
        captured.append({"cmd": cmd, "cwd": cwd, "env": env, "override": override})
        return 0

    monkeypatch.setattr(up, "_run", _fake_run)
    return captured


def test_prod_up_uses_packaged_stack_with_locked_images(station: Path, prod_calls: list[dict]):
    assert up.run_up(_config(station, "[station]\n"), detach=True) == 0
    call = prod_calls[0]
    cmd = call["cmd"]
    assert cmd[cmd.index("--project-directory") + 1] == str(station)
    assert cmd[cmd.index("-f") + 1] == str(up.PROD_COMPOSE_FILE)
    assert "--build" not in cmd
    assert cmd[-2:] == ["up", "-d"]
    assert call["env"]["PLUGINLAKE_IMAGE_API"] == _IMAGE_ENV["PLUGINLAKE_IMAGE_API"]
    assert call["env"][up.STACK_DIR_VAR] == str(up.STACK_DIR)


def test_prod_up_sets_lineage_on_code_server(station: Path, prod_calls: list[dict]):
    assert up.run_up(_config(station, '[station]\nlineage = true\nlineage_namespace = "ds1"\n')) == 0
    env = prod_calls[0]["override"]["services"]["dagster-code-server"]["environment"]
    assert env == {"OPENLINEAGE_URL": "http://marquez:5000", "OPENLINEAGE_NAMESPACE": "ds1"}
    assert "lineage" in _profiles_in(prod_calls[0]["cmd"])


def test_prod_up_without_released_images(tmp_path: Path, prod_calls: list[dict], capsys: pytest.CaptureFixture[str]):
    (tmp_path / ".env.production").write_text("", encoding="utf-8")
    assert up.run_up(_config(tmp_path, "[station]\n")) == 1
    assert not prod_calls
    assert "no released images" in capsys.readouterr().err


def test_prod_up_rejects_projects(station: Path, prod_calls: list[dict], capsys: pytest.CaptureFixture[str]):
    config = _config(station, '[[projects]]\nname = "demo"\nsource = "demo==1.0"\n')
    assert up.run_up(config) == 1
    assert not prod_calls
    assert "--dev" in capsys.readouterr().err


def test_prod_up_requires_env_file(station: Path, prod_calls: list[dict], capsys: pytest.CaptureFixture[str]):
    (station / ".env.production").unlink()
    assert up.run_up(_config(station, "[station]\n")) == 1
    assert "env.production.example" in capsys.readouterr().err


def test_prod_up_rejects_open_secrets_dir(station: Path, prod_calls: list[dict], capsys: pytest.CaptureFixture[str]):
    (station / "secrets").chmod(0o755)
    assert up.run_up(_config(station, "[station]\n")) == 1
    assert "chmod 700" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("toml", "secret"),
    [("[station]\n", "ducklake_pg_password"), ("[station]\nlineage = true\n", "marquez_db_password")],
)
def test_prod_up_requires_secret_files(
    station: Path, prod_calls: list[dict], capsys: pytest.CaptureFixture[str], toml: str, secret: str
):
    (station / "secrets" / secret).write_text("", encoding="utf-8")
    assert up.run_up(_config(station, toml)) == 1
    assert secret in capsys.readouterr().err


def test_prod_up_creates_empty_remote_write_secret(station: Path, prod_calls: list[dict]):
    assert up.run_up(_config(station, "[monitoring]\nenabled = true\n")) == 0
    remote_write = station / "secrets" / "prometheus_remote_write_password"
    assert remote_write.read_text(encoding="utf-8") == ""
    assert remote_write.stat().st_mode & 0o004


def test_prod_down_uses_station_dir(station: Path, prod_calls: list[dict]):
    assert up.run_down(volumes=True, config_path=station / "pluginlake.toml") == 0
    cmd = prod_calls[0]["cmd"]
    assert cmd[cmd.index("--project-directory") + 1] == str(station)
    assert _profiles_in(cmd) == ["ui", "lineage", "monitoring"]
    assert cmd[-2:] == ["down", "-v"]
