"""Tests for FHIR folder ingestion sensor."""

import json
import os
import time

import pytest
from dagster import SensorResult, SkipReason, build_sensor_context

from pluginlake.assets.fhir_sensor import fhir_folder_sensor


@pytest.fixture
def raw_dir(tmp_path, monkeypatch):
    fake_settings = type(
        "FakeSettings",
        (),
        {
            "raw_data_dir": tmp_path,
            "folder_watch_debounce_seconds": 60,
            "folder_watch_interval": 30,
        },
    )()
    monkeypatch.setattr(
        "pluginlake.assets.fhir_sensor.get_fhir_settings",
        lambda: fake_settings,
    )
    return tmp_path


def _write_ndjson(raw_dir, name, mtime_offset=-120):
    path = raw_dir / f"{name}.ndjson"
    path.write_text('{"id": "1"}\n')
    target_time = time.time() + mtime_offset
    os.utime(path, (target_time, target_time))
    return path


def test_skip_when_directory_empty(raw_dir):
    context = build_sensor_context()
    result = fhir_folder_sensor(context)
    assert isinstance(result, SkipReason)


def test_skip_when_directory_does_not_exist(raw_dir):
    import shutil

    shutil.rmtree(raw_dir)
    context = build_sensor_context()
    result = fhir_folder_sensor(context)
    assert isinstance(result, SkipReason)
    assert "does not exist" in (result.skip_message or "")


def test_yields_run_request_for_new_ndjson(raw_dir):
    _write_ndjson(raw_dir, "patient")
    context = build_sensor_context()
    result = fhir_folder_sensor(context)
    assert isinstance(result, SensorResult)
    assert result.run_requests is not None
    assert len(result.run_requests) == 1
    asset_keys = result.run_requests[0].asset_selection
    assert asset_keys is not None
    assert any(k.path[-1] == "patient" for k in asset_keys)


def test_skip_when_cursor_matches_mtime(raw_dir):
    path = _write_ndjson(raw_dir, "patient")
    mtime = path.stat().st_mtime
    cursor = json.dumps({"patient": mtime})
    context = build_sensor_context(cursor=cursor)
    result = fhir_folder_sensor(context)
    assert isinstance(result, SkipReason)


def test_ignores_non_ndjson_files(raw_dir):
    (raw_dir / "patient.csv").write_text("col1\n1\n")
    context = build_sensor_context()
    result = fhir_folder_sensor(context)
    assert isinstance(result, SkipReason)


def test_ignores_unknown_resource_types(raw_dir):
    _write_ndjson(raw_dir, "unknown_type")
    context = build_sensor_context()
    result = fhir_folder_sensor(context)
    assert isinstance(result, SkipReason)


def test_skips_recently_modified_files(raw_dir):
    _write_ndjson(raw_dir, "patient", mtime_offset=0)
    context = build_sensor_context()
    result = fhir_folder_sensor(context)
    assert isinstance(result, SkipReason)


def test_includes_omop_target_in_asset_selection(raw_dir):
    _write_ndjson(raw_dir, "patient")
    context = build_sensor_context()
    result = fhir_folder_sensor(context)
    assert isinstance(result, SensorResult)
    assert result.run_requests is not None
    keys = result.run_requests[0].asset_selection
    assert keys is not None
    key_paths = [k.path for k in keys]
    assert ["fhir_raw", "patient"] in key_paths
    assert ["fhir_omop_raw", "person"] in key_paths
    assert ["omop", "person"] in key_paths
