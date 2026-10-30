"""Tests for the Docker pre-check."""

import subprocess

from pluginlake.cli import stack


def _fake_run(failing: tuple[str, ...]):
    def fake(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1 if tuple(cmd) == failing else 0)

    return fake


def test_check_docker_reports_missing_binary(monkeypatch):
    monkeypatch.setattr(stack.shutil, "which", lambda _name: None)

    assert "not installed" in str(stack.check_docker())


def test_check_docker_reports_missing_compose_plugin(monkeypatch):
    monkeypatch.setattr(stack.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(stack.subprocess, "run", _fake_run(("docker", "compose", "version")))

    assert "Compose plugin" in str(stack.check_docker())


def test_check_docker_reports_unreachable_daemon(monkeypatch):
    monkeypatch.setattr(stack.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(stack.subprocess, "run", _fake_run(("docker", "info")))

    assert "daemon" in str(stack.check_docker())


def test_check_docker_passes_when_everything_is_available(monkeypatch):
    monkeypatch.setattr(stack.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(stack.subprocess, "run", _fake_run(("nothing",)))

    assert stack.check_docker() is None
