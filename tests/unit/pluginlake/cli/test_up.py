"""Tests for ``pluginlake up`` and ``pluginlake down``."""

import pytest

from pluginlake.cli import up as up_cli
from pluginlake.cli.main import main
from pluginlake.cli.project import run_project_demo

CONFIG = """
[station]
endpoint_url = "http://localhost:8000"

[[projects]]
name = "demo"
source = "demo==1.0"
"""


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "pluginlake.toml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def commands(monkeypatch):
    """Record every command passed to ``run`` and pretend Docker is available."""
    recorded: list[list[str]] = []
    monkeypatch.setattr(up_cli, "check_docker", lambda: None)
    monkeypatch.setattr(up_cli, "run", lambda cmd, **_kwargs: recorded.append(cmd) or 0)
    return recorded


def test_up_stops_with_message_when_docker_is_missing(monkeypatch, config_path, capsys):
    monkeypatch.setattr(up_cli, "check_docker", lambda: "Docker is not installed.")

    assert up_cli.run_up(config_path) == 1
    assert "Docker is not installed." in capsys.readouterr().err


def test_up_waits_for_healthy_services_in_the_background(commands, config_path):
    assert up_cli.run_up(config_path) == 0

    assert commands[0][-4:] == ["up", "-d", "--wait", "--build"]


def test_up_no_build_skips_rebuild(commands, config_path):
    assert up_cli.run_up(config_path, build=False) == 0

    assert "--build" not in commands[0]


def test_up_attach_follows_logs_after_healthy(commands, config_path):
    assert up_cli.run_up(config_path, attach=True) == 0

    assert commands[1][-2:] == ["logs", "-f"]


def test_up_failure_returns_code_and_skips_attach(monkeypatch, config_path, capsys):
    calls: list[list[str]] = []
    monkeypatch.setattr(up_cli, "check_docker", lambda: None)
    monkeypatch.setattr(up_cli, "run", lambda cmd, **_kwargs: calls.append(cmd) or 1)

    assert up_cli.run_up(config_path, attach=True) == 1
    assert len(calls) == 1
    assert "pluginlake status" in capsys.readouterr().err


def test_down_never_removes_volumes(commands, config_path):
    assert up_cli.run_down(config_path) == 0

    assert commands[0][-1] == "down"
    assert "-v" not in commands[0]
    assert "--volumes" not in commands[0]


def test_down_has_no_volumes_option(config_path):
    assert main(["down", "--config", str(config_path), "--volumes"]) != 0


def test_demo_scaffolds_the_project_and_deploys_it(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(
        "pluginlake.cli.project.run_up",
        lambda config_path, **kwargs: seen.update(config=config_path, build=kwargs["build"]) or 0,
    )
    assert run_project_demo(build=False, workdir=tmp_path) == 0
    assert (tmp_path / "demo" / "pyproject.toml").is_file()
    assert seen["config"] == tmp_path / "pluginlake.demo.toml"
    assert 'path = "demo"' in seen["config"].read_text()
    assert seen["build"] is False
