"""Tests for pluginlake.assets.fhir."""

from unittest.mock import MagicMock

import orjson
import polars as pl
from dagster import AssetKey

from pluginlake.assets.fhir import fhir_raw_tables, fhir_to_omop_tables
from pluginlake.fhir.config import FHIRSettings


def _build_context(asset_keys: list[AssetKey]) -> MagicMock:
    ctx = MagicMock()
    ctx.selected_asset_keys = set(asset_keys)
    return ctx


def _patch_fhir_settings(monkeypatch, raw_data_dir):
    monkeypatch.setattr(
        "pluginlake.fhir.loader.get_fhir_settings",
        lambda: FHIRSettings(raw_data_dir=raw_data_dir),
    )


def test_fhir_raw_tables_loads_ndjson(tmp_path, monkeypatch):
    patient_data = [
        orjson.dumps({"resourceType": "Patient", "id": "1", "birthDate": "1990-01-01"}),
        orjson.dumps({"resourceType": "Patient", "id": "2", "birthDate": "1985-06-15"}),
    ]
    (tmp_path / "patient.ndjson").write_bytes(b"\n".join(patient_data) + b"\n")

    _patch_fhir_settings(monkeypatch, tmp_path)

    _raw_fn = fhir_raw_tables.op.compute_fn.decorated_fn  # type: ignore[union-attr]
    context = _build_context([AssetKey(["fhir_raw", "patient"])])
    outputs = list(_raw_fn(context))
    assert len(outputs) == 1
    df = outputs[0].value
    assert isinstance(df, pl.DataFrame)
    assert df.columns == ["json_data"]
    assert len(df) == 2


def test_fhir_raw_tables_skips_missing(tmp_path, monkeypatch):
    _patch_fhir_settings(monkeypatch, tmp_path)

    _raw_fn = fhir_raw_tables.op.compute_fn.decorated_fn  # type: ignore[union-attr]
    context = _build_context([AssetKey(["fhir_raw", "patient"])])
    outputs = list(_raw_fn(context))
    assert len(outputs) == 0


def test_fhir_raw_dependency_on_fhir_to_omop():
    deps = fhir_to_omop_tables.asset_deps
    raw_patient_key = AssetKey(["fhir_raw", "patient"])
    all_dep_keys = set()
    for dep_set in deps.values():
        all_dep_keys.update(dep_set)
    assert raw_patient_key in all_dep_keys
