"""Tests for pluginlake.fhir.config."""

from pathlib import Path

import pytest

from pluginlake.fhir.config import FHIRSettings, get_fhir_settings


def test_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FHIR_RAW_DATA_DIR", raising=False)
    s = FHIRSettings(_env_file=None)  # ty: ignore[unknown-argument] — Pydantic Settings runtime param
    assert s.raw_data_dir == Path(".data/raw/fhir")
    assert s.folder_watch_interval == 30
    assert s.folder_watch_debounce_seconds == 60


def test_from_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FHIR_RAW_DATA_DIR", str(tmp_path / "fhir"))
    monkeypatch.setenv("FHIR_FOLDER_WATCH_INTERVAL", "10")
    s = FHIRSettings()
    assert s.raw_data_dir == tmp_path / "fhir"
    assert s.folder_watch_interval == 10


def test_get_fhir_settings():
    s = get_fhir_settings()
    assert isinstance(s, FHIRSettings)
