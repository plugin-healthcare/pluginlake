"""Tests for ``pluginlake up`` / ``pluginlake down`` compose command assembly."""

import json
from pathlib import Path

import pytest

from pluginlake.cli import up as up_cli


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Capture compose invocations (command and override contents) instead of running them."""
    captured: list[dict] = []

    def _fake_run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> int:
        files = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-f"]
        override = json.loads(Path(files[1]).read_text(encoding="utf-8")) if len(files) > 1 else None
        captured.append({"cmd": cmd, "override": override, "env": env})
        return 0

    monkeypatch.setattr(up_cli, "_run", _fake_run)
    return captured


def _config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "pluginlake.toml"
    path.write_text(body, encoding="utf-8")
    return path


def _profiles(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--profile"]


def test_up_without_monitoring(tmp_path: Path, calls: list[dict]):
    assert up_cli.run_up(_config(tmp_path, "[station]\n")) == 0
    cmd, override = calls[0]["cmd"], calls[0]["override"]
    assert "monitoring" not in _profiles(cmd)
    assert "prometheus" not in override["services"]


def test_up_with_monitoring(tmp_path: Path, calls: list[dict]):
    config = _config(tmp_path, '[monitoring]\nenabled = true\nstation_id = "ds-001"\n')
    assert up_cli.run_up(config, detach=True) == 0
    cmd, override = calls[0]["cmd"], calls[0]["override"]
    assert "monitoring" in _profiles(cmd)
    assert "--scale" not in cmd
    assert override["services"]["prometheus"]["environment"] == {
        "PROMETHEUS_STATION_ID": "ds-001",
        "PROMETHEUS_SCRAPE_CADVISOR": "true",
    }


def test_up_with_remote_write(tmp_path: Path, calls: list[dict]):
    url = "https://central.example.org/api/v1/write"
    config = _config(tmp_path, f'[monitoring]\nenabled = true\nremote_write_url = "{url}"\n')
    up_cli.run_up(config)
    env = calls[0]["override"]["services"]["prometheus"]["environment"]
    assert env["PROMETHEUS_REMOTE_WRITE_URL"] == url
    assert not any("PASSWORD" in key for key in env)


def test_up_without_cadvisor_scales_it_to_zero(tmp_path: Path, calls: list[dict]):
    config = _config(tmp_path, "[monitoring]\nenabled = true\ncadvisor = false\n")
    up_cli.run_up(config)
    cmd, override = calls[0]["cmd"], calls[0]["override"]
    assert cmd[cmd.index("--scale") + 1] == "cadvisor=0"
    assert cmd.index("--scale") > cmd.index("up")
    assert override["services"]["prometheus"]["environment"]["PROMETHEUS_SCRAPE_CADVISOR"] == "false"


def test_up_invalid_monitoring_config(tmp_path: Path, calls: list[dict], capsys: pytest.CaptureFixture[str]):
    config = _config(tmp_path, '[monitoring]\nremote_write_url = "not-a-url"\n')
    assert up_cli.run_up(config) == 1
    assert not calls
    assert "Invalid station config" in capsys.readouterr().err


def test_down_always_includes_monitoring(tmp_path: Path, calls: list[dict]):
    assert up_cli.run_down(_config(tmp_path, "[monitoring]\nenabled = false\n")) == 0
    cmd = calls[0]["cmd"]
    assert "monitoring" in _profiles(cmd)
    assert cmd[-1] == "down"


def test_compose_env_untouched_without_monitoring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(up_cli.REMOTE_WRITE_SECRET_VAR, raising=False)
    assert up_cli._compose_env(tmp_path, monitoring=False) is None


def test_compose_env_defaults_remote_write_password_to_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(up_cli.REMOTE_WRITE_SECRET_VAR, raising=False)
    (tmp_path / ".env").write_text("POSTGRES_PASSWORD=x\n", encoding="utf-8")
    env = up_cli._compose_env(tmp_path, monitoring=True)
    assert env is not None
    assert env[up_cli.REMOTE_WRITE_SECRET_VAR] == ""


@pytest.mark.parametrize("line", ["PROMETHEUS_REMOTE_WRITE_PASSWORD=s3cret", "PROMETHEUS_REMOTE_WRITE_PASSWORD="])
def test_compose_env_keeps_password_from_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: str):
    monkeypatch.delenv(up_cli.REMOTE_WRITE_SECRET_VAR, raising=False)
    (tmp_path / ".env").write_text(f"{line}\n", encoding="utf-8")
    assert up_cli._compose_env(tmp_path, monitoring=True) is None


def test_compose_env_keeps_password_from_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(up_cli.REMOTE_WRITE_SECRET_VAR, "s3cret")
    assert up_cli._compose_env(tmp_path, monitoring=True) is None
