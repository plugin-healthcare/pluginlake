"""Tests for OMOP folder ingestion sensor."""

import json
import time

import pytest
from dagster import SensorResult, SkipReason, build_sensor_context

from pluginlake.assets.omop_sensor import omop_folder_sensor


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
        "pluginlake.assets.omop_sensor.get_omop_settings",
        lambda: fake_settings,
    )
    return tmp_path


def _write_csv(raw_dir, name, mtime_offset=-120):
    path = raw_dir / f"{name}.csv"
    path.write_text("col1,col2\n1,2\n")
    import os

    target_time = time.time() + mtime_offset
    os.utime(path, (target_time, target_time))
    return path


def test_skip_when_directory_empty(raw_dir):
    context = build_sensor_context()
    result = omop_folder_sensor(context)
    assert isinstance(result, SkipReason)
    assert result.skip_message == "No new or modified OMOP CSV files detected"


def test_skip_when_directory_does_not_exist(raw_dir):
    import shutil

    shutil.rmtree(raw_dir)
    context = build_sensor_context()
    result = omop_folder_sensor(context)
    assert isinstance(result, SkipReason)
    assert result.skip_message is not None
    assert "does not exist" in result.skip_message


def test_yields_run_request_for_new_csv(raw_dir):
    _write_csv(raw_dir, "person")
    context = build_sensor_context()
    result = omop_folder_sensor(context)
    assert isinstance(result, SensorResult)
    assert result.run_requests is not None
    assert len(result.run_requests) == 1
    asset_keys = result.run_requests[0].asset_selection
    assert asset_keys is not None
    assert any(k.path[-1] == "person" for k in asset_keys)


def test_skip_when_cursor_matches_mtime(raw_dir):
    path = _write_csv(raw_dir, "person")
    mtime = path.stat().st_mtime
    cursor = json.dumps({"person": mtime})
    context = build_sensor_context(cursor=cursor)
    result = omop_folder_sensor(context)
    assert isinstance(result, SkipReason)
    assert result.skip_message is not None


def test_yields_run_request_for_modified_csv(raw_dir):
    path = _write_csv(raw_dir, "person", mtime_offset=-200)
    old_mtime = path.stat().st_mtime
    cursor = json.dumps({"person": old_mtime})

    _write_csv(raw_dir, "person", mtime_offset=-120)
    context = build_sensor_context(cursor=cursor)
    result = omop_folder_sensor(context)
    assert isinstance(result, SensorResult)
    assert result.run_requests is not None
    assert len(result.run_requests) == 1


def test_ignores_non_csv_files(raw_dir):
    (raw_dir / "person.parquet").write_text("not csv")
    context = build_sensor_context()
    result = omop_folder_sensor(context)
    assert isinstance(result, SkipReason)
    assert result.skip_message is not None


def test_ignores_non_omop_table_names(raw_dir):
    _write_csv(raw_dir, "not_an_omop_table")
    context = build_sensor_context()
    result = omop_folder_sensor(context)
    assert isinstance(result, SkipReason)
    assert result.skip_message is not None


def test_skips_recently_modified_files(raw_dir):
    _write_csv(raw_dir, "person", mtime_offset=0)
    context = build_sensor_context()
    result = omop_folder_sensor(context)
    assert isinstance(result, SkipReason)
    assert result.skip_message is not None


def test_cursor_updates_correctly(raw_dir):
    _write_csv(raw_dir, "person")
    context = build_sensor_context()
    omop_folder_sensor(context)
    assert context.cursor is not None
    cursor = json.loads(context.cursor)
    assert "person" in cursor
    assert isinstance(cursor["person"], float)
