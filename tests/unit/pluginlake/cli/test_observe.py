"""Tests for ``pluginlake status`` and ``pluginlake logs``."""

import json

import pytest

from pluginlake.cli import observe


def _container(service, state="running", health=""):
    return {"Service": service, "State": state, "Health": health}


@pytest.fixture
def docker_available(monkeypatch):
    monkeypatch.setattr(observe, "check_docker", lambda: None)


def _stub_ps(monkeypatch, containers):
    stdout = "\n".join(json.dumps(c) for c in containers)
    monkeypatch.setattr(observe, "capture", lambda *_args, **_kwargs: (0, stdout))


def test_parse_ps_output_accepts_array_and_lines():
    containers = [_container("a"), _container("b")]

    assert observe.parse_ps_output(json.dumps(containers)) == containers
    assert observe.parse_ps_output("\n".join(json.dumps(c) for c in containers)) == containers
    assert observe.parse_ps_output("") == []


def test_status_is_zero_when_all_running_and_healthy(docker_available, monkeypatch, tmp_path, capsys):
    _stub_ps(monkeypatch, [_container("dagster", health="healthy"), _container("pluginlake")])

    assert observe.run_status(tmp_path / "pluginlake.toml") == 0
    assert "dagster" in capsys.readouterr().out


@pytest.mark.parametrize(
    "containers",
    [
        [_container("dagster", health="unhealthy")],
        [_container("dagster", health="starting")],
        [_container("dagster", state="exited")],
        [],
    ],
)
def test_status_is_one_when_a_service_is_not_ok(docker_available, monkeypatch, tmp_path, containers):
    _stub_ps(monkeypatch, containers)

    assert observe.run_status(tmp_path / "pluginlake.toml") == 1


def test_status_reports_missing_docker(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(observe, "check_docker", lambda: "Docker is not installed.")

    assert observe.run_status(tmp_path / "pluginlake.toml") == 1
    assert "Docker is not installed." in capsys.readouterr().err


def test_logs_passes_follow_and_service(docker_available, monkeypatch, tmp_path):
    recorded: list[list[str]] = []
    monkeypatch.setattr(observe, "run", lambda cmd, **_kwargs: recorded.append(cmd) or 0)

    assert observe.run_logs(tmp_path / "pluginlake.toml", "dagster", follow=True) == 0
    assert recorded[0][-3:] == ["logs", "-f", "dagster"]
