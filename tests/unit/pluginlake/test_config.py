"""Tests for pluginlake.config."""

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from pluginlake.config import (
    DagsterSettings,
    LogLevel,
    PostgresSettings,
    ServerSettings,
    Settings,
    StorageLayer,
    StorageSettings,
)


def test_defaults(settings):
    assert settings.debug is False
    assert settings.verbose is False
    assert settings.log_level == LogLevel.INFO


def test_debug_overrides_log_level():
    s = Settings(debug=True, log_level=LogLevel.WARNING)
    assert s.effective_log_level == logging.DEBUG


def test_verbose_overrides_log_level():
    s = Settings(verbose=True, log_level=LogLevel.WARNING)
    assert s.effective_log_level == logging.DEBUG


def test_effective_log_level():
    s = Settings(log_level=LogLevel.ERROR)
    assert s.effective_log_level == logging.ERROR


def test_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLUGINLAKE_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("PLUGINLAKE_DEBUG", "true")
    s = Settings()
    assert s.log_level == LogLevel.WARNING
    assert s.debug is True


def test_storage_layer_values():
    assert StorageLayer.RAW == "raw"
    assert StorageLayer.PROCESSED == "processed"
    assert StorageLayer.OUTPUT == "output"


def test_storage_layer_iteration():
    layers = list(StorageLayer)
    assert len(layers) == len(StorageLayer)


def test_storage_settings_defaults():
    s = StorageSettings()
    assert s.base_dir.is_absolute()
    assert s.backend == "local"


def test_storage_settings_resolves_to_absolute(tmp_path: Path):
    s = StorageSettings(base_dir=tmp_path / "relative")
    assert s.base_dir.is_absolute()


def test_storage_settings_layer_dirs(tmp_path: Path):
    s = StorageSettings(base_dir=tmp_path / "lake")
    assert s.raw_dir == tmp_path / "lake" / "raw"
    assert s.processed_dir == tmp_path / "lake" / "processed"
    assert s.output_dir == tmp_path / "lake" / "output"


def test_storage_settings_get_layer_path(tmp_path: Path):
    s = StorageSettings(base_dir=tmp_path / "lake")
    path = s.get_layer_path(StorageLayer.RAW, "patients", "file.parquet")
    assert path == tmp_path / "lake" / "raw" / "patients" / "file.parquet"


def test_storage_settings_get_layer_path_no_parts(tmp_path: Path):
    s = StorageSettings(base_dir=tmp_path / "lake")
    path = s.get_layer_path(StorageLayer.OUTPUT)
    assert path == tmp_path / "lake" / "output"


def test_storage_settings_ensure_directories(tmp_path: Path):
    s = StorageSettings(base_dir=tmp_path / "lake")
    s.ensure_directories()
    assert (tmp_path / "lake" / "raw").is_dir()
    assert (tmp_path / "lake" / "processed").is_dir()
    assert (tmp_path / "lake" / "output").is_dir()


def test_storage_settings_ensure_directories_idempotent(tmp_path: Path):
    s = StorageSettings(base_dir=tmp_path / "lake")
    s.ensure_directories()
    s.ensure_directories()
    assert (tmp_path / "lake" / "raw").is_dir()


def test_storage_settings_layer_dirs_property(tmp_path: Path):
    s = StorageSettings(base_dir=tmp_path / "lake")
    dirs = s.layer_dirs
    assert len(dirs) == len(StorageLayer)
    assert dirs[StorageLayer.RAW] == tmp_path / "lake" / "raw"
    assert dirs[StorageLayer.PROCESSED] == tmp_path / "lake" / "processed"
    assert dirs[StorageLayer.OUTPUT] == tmp_path / "lake" / "output"


def test_storage_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("PLUGINLAKE_STORAGE_BASE_DIR", str(tmp_path / "envdata"))
    monkeypatch.setenv("PLUGINLAKE_STORAGE_BACKEND", "local")
    s = StorageSettings()
    assert s.base_dir == tmp_path / "envdata"
    assert s.backend == "local"


def test_server_settings_defaults():
    s = ServerSettings()
    assert s.host == "0.0.0.0"  # noqa: S104
    assert s.port == ServerSettings.model_fields["port"].default


def test_server_settings_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLUGINLAKE_SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("PLUGINLAKE_SERVER_PORT", "9090")
    s = ServerSettings()
    assert s.host == "127.0.0.1"
    assert s.port == 9090


def test_postgres_settings_missing_required_fields():
    with pytest.raises(ValidationError):
        PostgresSettings()  # type: ignore[missing-argument]


def test_postgres_settings_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLUGINLAKE_POSTGRES_USER", "admin")
    monkeypatch.setenv("PLUGINLAKE_POSTGRES_PASSWORD", "secret")
    s = PostgresSettings()  # type: ignore[missing-argument]
    assert s.user.get_secret_value() == "admin"
    assert s.password.get_secret_value() == "secret"


def test_postgres_settings_error_lists_missing_fields():
    with pytest.raises(ValidationError) as exc_info:
        PostgresSettings()  # type: ignore[missing-argument]
    errors = exc_info.value.errors()
    missing_fields = {e["loc"][0] for e in errors}
    assert "user" in missing_fields
    assert "password" in missing_fields


def test_dagster_settings_missing_required_fields():
    with pytest.raises(ValidationError):
        DagsterSettings()  # type: ignore[missing-argument]


def test_dagster_settings_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLUGINLAKE_DAGSTER_PG_USER", "dagster")
    monkeypatch.setenv("PLUGINLAKE_DAGSTER_PG_PASSWORD", "secret")
    s = DagsterSettings()  # type: ignore[missing-argument]
    assert s.pg_user.get_secret_value() == "dagster"


def test_dagster_settings_error_lists_missing_fields():
    with pytest.raises(ValidationError) as exc_info:
        DagsterSettings()  # type: ignore[missing-argument]
    errors = exc_info.value.errors()
    missing_fields = {e["loc"][0] for e in errors}
    assert "pg_user" in missing_fields
    assert "pg_password" in missing_fields


def test_all_default_configs_load():
    """All settings classes with only optional fields instantiate without error."""
    Settings()
    StorageSettings()
    ServerSettings()


def test_invalid_log_level_gives_clear_error():
    with pytest.raises(ValidationError, match="log_level"):
        Settings(log_level="NONEXISTENT")  # type: ignore[invalid-argument-type]


def test_invalid_storage_backend_gives_clear_error():
    with pytest.raises(ValidationError, match="backend"):
        StorageSettings(backend="s3")  # type: ignore[invalid-argument-type]


def test_storage_layers_writable_after_ensure(tmp_path: Path):
    s = StorageSettings(base_dir=tmp_path / "lake")
    s.ensure_directories()
    for layer_dir in s.layer_dirs.values():
        assert layer_dir.is_dir()
        test_file = layer_dir / "_write_test"
        test_file.write_text("ok")
        assert test_file.read_text() == "ok"
        test_file.unlink()


def test_storage_layers_writable_via_get_layer_path(tmp_path: Path):
    s = StorageSettings(base_dir=tmp_path / "lake")
    s.ensure_directories()
    target = s.get_layer_path(StorageLayer.RAW, "test.parquet")
    target.write_text("data")
    assert target.read_text() == "data"
