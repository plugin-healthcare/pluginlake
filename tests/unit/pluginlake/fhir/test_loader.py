"""Tests for pluginlake.fhir.loader."""

import orjson
import polars as pl
import pytest

from pluginlake.fhir.config import FHIRSettings
from pluginlake.fhir.loader import load_fhir_dataset, load_fhir_ndjson


def _patch_fhir_settings(monkeypatch, raw_data_dir):
    monkeypatch.setattr(
        "pluginlake.fhir.loader.get_fhir_settings",
        lambda: FHIRSettings(raw_data_dir=raw_data_dir),
    )


@pytest.fixture
def ndjson_file(tmp_path):
    path = tmp_path / "patient.ndjson"
    lines = [
        orjson.dumps({"resourceType": "Patient", "id": "1", "birthDate": "1990-01-01"}),
        orjson.dumps({"resourceType": "Patient", "id": "2", "birthDate": "1985-06-15"}),
    ]
    path.write_bytes(b"\n".join(lines) + b"\n")
    return path


def test_load_fhir_ndjson(ndjson_file):
    df = load_fhir_ndjson(ndjson_file)
    assert isinstance(df, pl.DataFrame)
    assert df.columns == ["json_data"]
    assert df.dtypes == [pl.Utf8]
    assert len(df) == 2


def test_load_fhir_ndjson_skips_invalid_lines(tmp_path):
    path = tmp_path / "bad.ndjson"
    path.write_bytes(b'{"id": "1"}\nnot json\n{"id": "2"}\n')
    df = load_fhir_ndjson(path)
    assert len(df) == 2


def test_load_fhir_ndjson_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_fhir_ndjson(tmp_path / "nonexistent.ndjson")


def test_load_fhir_ndjson_empty_file(tmp_path):
    path = tmp_path / "empty.ndjson"
    path.write_bytes(b"")
    df = load_fhir_ndjson(path)
    assert len(df) == 0


def test_load_fhir_dataset(tmp_path, monkeypatch):
    _patch_fhir_settings(monkeypatch, tmp_path)
    (tmp_path / "patient.ndjson").write_bytes(orjson.dumps({"id": "1"}) + b"\n")
    (tmp_path / "encounter.ndjson").write_bytes(orjson.dumps({"id": "2"}) + b"\n")

    result = load_fhir_dataset(data_dir=tmp_path)
    assert "patient" in result
    assert "encounter" in result
    assert len(result["patient"]) == 1


def test_load_fhir_dataset_filters_by_type(tmp_path, monkeypatch):
    _patch_fhir_settings(monkeypatch, tmp_path)
    (tmp_path / "patient.ndjson").write_bytes(orjson.dumps({"id": "1"}) + b"\n")
    (tmp_path / "encounter.ndjson").write_bytes(orjson.dumps({"id": "2"}) + b"\n")

    result = load_fhir_dataset(data_dir=tmp_path, resource_types=["patient"])
    assert "patient" in result
    assert "encounter" not in result


def test_load_fhir_dataset_missing_dir(tmp_path, monkeypatch):
    _patch_fhir_settings(monkeypatch, tmp_path / "nope")
    result = load_fhir_dataset(data_dir=tmp_path / "nope")
    assert result == {}
