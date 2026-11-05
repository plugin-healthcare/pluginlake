"""Tests for the DuckLake settings."""

from pathlib import Path

import pytest

from pluginlake.core.config import DuckLakeSettings


@pytest.fixture
def ducklake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKLAKE_PG_HOST", "postgres")
    monkeypatch.setenv("DUCKLAKE_PG_USER", "dagster")
    monkeypatch.setenv("DUCKLAKE_PG_DB", "ducklake")
    monkeypatch.delenv("DUCKLAKE_PG_PASSWORD", raising=False)


@pytest.mark.usefixtures("ducklake_env")
def test_password_from_secret_file(tmp_path: Path):
    (tmp_path / "ducklake_pg_password").write_text("from-secret", encoding="utf-8")
    settings = DuckLakeSettings(_env_file=None, _secrets_dir=tmp_path)  # type: ignore[missing-argument]
    assert settings.pg_password.get_secret_value() == "from-secret"
    assert "password=from-secret" in settings.pg_connection_string


@pytest.mark.usefixtures("ducklake_env")
def test_password_is_hidden_in_repr(tmp_path: Path):
    (tmp_path / "ducklake_pg_password").write_text("from-secret", encoding="utf-8")
    settings = DuckLakeSettings(_env_file=None, _secrets_dir=tmp_path)  # type: ignore[missing-argument]
    assert "from-secret" not in repr(settings)
