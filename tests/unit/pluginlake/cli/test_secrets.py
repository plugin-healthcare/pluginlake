"""Tests for ``pluginlake secrets``."""

from pathlib import Path

import pytest

from pluginlake.cli.secrets import run_secrets_get, run_secrets_list
from pluginlake.deploy.init_secrets import init_home


@pytest.fixture
def home(tmp_path: Path) -> Path:
    init_home(tmp_path, uid=1000, gid=1000)
    return tmp_path


def test_list_shows_names_without_values(home: Path, capsys: pytest.CaptureFixture[str]):
    assert run_secrets_list(home) == 0
    out = capsys.readouterr().out
    password = (home / "secrets" / "postgres_password").read_text(encoding="utf-8")
    assert "postgres_password" in out
    assert password not in out


def test_list_fails_when_an_internal_secret_is_missing(home: Path, capsys: pytest.CaptureFixture[str]):
    (home / "secrets" / "postgres_password").unlink()
    assert run_secrets_list(home) == 1
    assert "MISSING" in capsys.readouterr().out


def test_get_prints_the_value_and_logs_without_it(home: Path, capsys: pytest.CaptureFixture[str], caplog):
    caplog.set_level("INFO")
    value = (home / "secrets" / "postgres_password").read_text(encoding="utf-8")
    assert run_secrets_get(home, "postgres_password") == 0
    assert capsys.readouterr().out == value
    assert "postgres_password" in caplog.text
    assert value not in caplog.text


def test_get_rejects_unknown_secret(home: Path):
    assert run_secrets_get(home, "../etc/passwd") == 1
