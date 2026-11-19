"""Tests for the release helpers in scripts/release.py (used by the release workflow)."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[3] / "scripts" / "release.py"
_SPEC = importlib.util.spec_from_file_location("release_script", _PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release)

CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Upcoming.

## [0.2.0-rc.1] - 2026-11-12

### Added

- Release workflow.

## [0.1.1] - 2026-06-03

### Security

- Tornado.
"""


@pytest.mark.parametrize(
    ("tag", "pyproject", "expected"),
    [
        ("v0.2.0", "0.2.0", ("0.2.0", False)),
        ("v0.2.0-rc.1", "0.2.0-rc.1", ("0.2.0-rc.1", True)),
        ("v0.2.0-rc.1", "0.2.0rc1", ("0.2.0-rc.1", True)),
    ],
)
def test_check_tag_accepts_matching_version(tag: str, pyproject: str, expected: tuple[str, bool]):
    assert release.check_tag(tag, pyproject) == expected


@pytest.mark.parametrize(
    ("tag", "pyproject"),
    [
        ("v0.2.1", "0.2.0"),
        ("v0.2.0-rc.1", "0.2.0"),
        ("0.2.0", "0.2.0"),
        ("v0.2", "0.2.0"),
        ("v0.2.0-foo bar", "0.2.0"),
        ("v0.2.0-banana", "0.2.0"),
    ],
)
def test_check_tag_rejects(tag: str, pyproject: str):
    with pytest.raises(release.ReleaseError):
        release.check_tag(tag, pyproject)


def test_release_notes_extracts_section():
    notes = release.release_notes("0.2.0-rc.1", CHANGELOG)
    assert notes == "### Added\n\n- Release workflow.\n"


def test_release_notes_last_section():
    assert "Tornado" in release.release_notes("0.1.1", CHANGELOG)


@pytest.mark.parametrize("version", ["0.3.0", "0.2.0"])
def test_release_notes_missing_section(version: str):
    with pytest.raises(release.ReleaseError, match="no"):
        release.release_notes(version, CHANGELOG)


def test_main_writes_github_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(release, "project_version", lambda: "0.2.0-rc.1")
    assert release.main(["check-tag", "v0.2.0-rc.1"]) == 0
    assert output.read_text(encoding="utf-8") == "version=0.2.0-rc.1\nprerelease=true\n"


def test_main_fails_on_mismatch(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(release, "project_version", lambda: "0.2.0")
    assert release.main(["check-tag", "v9.9.9"]) == 1
    assert "::error::" in capsys.readouterr().err
