"""Tests for ``pluginlake verify``."""

from pluginlake.cli import verify as verify_cli
from pluginlake.plugins.manifest import ProjectManifest


def _patch_manifests(monkeypatch, manifests):
    monkeypatch.setattr(verify_cli, "discover_manifests", lambda: manifests)


def test_verify_returns_zero_when_conformant(monkeypatch, capsys):
    manifest = ProjectManifest(id="ok", catalog="ok", namespace="ok", config_prefix="OK_")
    _patch_manifests(monkeypatch, [manifest])

    assert verify_cli.run_verify() == 0
    assert "conform" in capsys.readouterr().out


def test_verify_returns_one_when_non_conformant(monkeypatch, capsys):
    manifest = ProjectManifest(
        id="bad",
        catalog="bad",
        namespace="bad",
        config_prefix="BAD_",
        requires_core=">=99.0.0",
    )
    _patch_manifests(monkeypatch, [manifest])

    assert verify_cli.run_verify() == 1
    assert "Conformance failed" in capsys.readouterr().err


def test_verify_reports_nothing_to_verify(monkeypatch, capsys):
    _patch_manifests(monkeypatch, [])
    assert verify_cli.run_verify() == 0
    assert "Nothing to verify" in capsys.readouterr().out


def test_verify_unknown_project_filter_returns_one(monkeypatch, capsys):
    manifest = ProjectManifest(id="ok", catalog="ok", namespace="ok", config_prefix="OK_")
    _patch_manifests(monkeypatch, [manifest])

    assert verify_cli.run_verify(project="missing") == 1
    assert "No installed project" in capsys.readouterr().err
