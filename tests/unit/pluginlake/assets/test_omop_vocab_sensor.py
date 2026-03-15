"""Tests for OMOP vocabulary auto-download and ingestion sensor."""

import json
import os
import time

import pytest
from dagster import SensorResult, SkipReason, build_sensor_context

from pluginlake.assets.omop_vocab_sensor import omop_vocab_sensor


@pytest.fixture
def vocab_dir(tmp_path, monkeypatch):
    fake_settings = type(
        "FakeSettings",
        (),
        {
            "vocabulary_dir": tmp_path,
            "vocabulary_auto_load": True,
            "folder_watch_interval": 30,
            "folder_watch_debounce_seconds": 60,
        },
    )()
    monkeypatch.setattr(
        "pluginlake.assets.omop_vocab_sensor.get_omop_settings",
        lambda: fake_settings,
    )
    return tmp_path


def _write_vocab_csv(vocab_dir, name, mtime_offset=-120):
    path = vocab_dir / f"{name.upper()}.csv"
    path.write_text("col1\tval1\n")
    target_time = time.time() + mtime_offset
    os.utime(path, (target_time, target_time))
    return path


def test_skip_when_auto_load_disabled(tmp_path, monkeypatch):
    fake_settings = type(
        "FakeSettings",
        (),
        {
            "vocabulary_dir": tmp_path,
            "vocabulary_auto_load": False,
            "folder_watch_interval": 30,
            "folder_watch_debounce_seconds": 60,
        },
    )()
    monkeypatch.setattr(
        "pluginlake.assets.omop_vocab_sensor.get_omop_settings",
        lambda: fake_settings,
    )
    context = build_sensor_context()
    result = omop_vocab_sensor(context)
    assert isinstance(result, SkipReason)
    assert result.skip_message is not None
    assert "disabled" in result.skip_message


def test_auto_provisions_when_directory_empty(vocab_dir, monkeypatch):
    called = []
    monkeypatch.setattr(
        "pluginlake.omop.provisioning.ensure_omop_vocabularies",
        lambda *_a, **_kw: called.append(True) or vocab_dir,
    )
    context = build_sensor_context()
    omop_vocab_sensor(context)
    assert called


def test_auto_provisions_when_directory_missing(tmp_path, monkeypatch):
    missing_dir = tmp_path / "nonexistent"
    fake_settings = type(
        "FakeSettings",
        (),
        {
            "vocabulary_dir": missing_dir,
            "vocabulary_auto_load": True,
            "folder_watch_interval": 30,
            "folder_watch_debounce_seconds": 60,
        },
    )()
    monkeypatch.setattr(
        "pluginlake.assets.omop_vocab_sensor.get_omop_settings",
        lambda: fake_settings,
    )
    called = []
    monkeypatch.setattr(
        "pluginlake.omop.provisioning.ensure_omop_vocabularies",
        lambda *_a, **_kw: called.append(True) or missing_dir,
    )
    context = build_sensor_context()
    omop_vocab_sensor(context)
    assert called


def test_download_failure_returns_skip_reason(vocab_dir, monkeypatch):
    import shutil

    shutil.rmtree(vocab_dir)

    fake_settings = type(
        "FakeSettings",
        (),
        {
            "vocabulary_dir": vocab_dir,
            "vocabulary_auto_load": True,
            "folder_watch_interval": 30,
            "folder_watch_debounce_seconds": 60,
        },
    )()
    monkeypatch.setattr(
        "pluginlake.assets.omop_vocab_sensor.get_omop_settings",
        lambda: fake_settings,
    )
    monkeypatch.setattr(
        "pluginlake.omop.provisioning.ensure_omop_vocabularies",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("Network error")),
    )
    context = build_sensor_context()
    result = omop_vocab_sensor(context)
    assert isinstance(result, SkipReason)
    assert result.skip_message is not None
    assert "failed" in result.skip_message.lower()


def test_yields_run_request_for_new_vocab_csv(vocab_dir):
    _write_vocab_csv(vocab_dir, "CONCEPT")
    context = build_sensor_context()
    result = omop_vocab_sensor(context)
    assert isinstance(result, SensorResult)
    assert result.run_requests is not None
    assert len(result.run_requests) == 1
    asset_keys = result.run_requests[0].asset_selection
    assert asset_keys is not None
    assert any(k.path[-1] == "concept" for k in asset_keys)


def test_skip_when_cursor_matches_mtime(vocab_dir):
    path = _write_vocab_csv(vocab_dir, "CONCEPT")
    mtime = path.stat().st_mtime
    cursor = json.dumps({"concept": mtime})
    context = build_sensor_context(cursor=cursor)
    result = omop_vocab_sensor(context)
    assert isinstance(result, SkipReason)


def test_yields_run_request_on_file_change(vocab_dir):
    path = _write_vocab_csv(vocab_dir, "CONCEPT", mtime_offset=-200)
    old_mtime = path.stat().st_mtime
    cursor = json.dumps({"concept": old_mtime})

    _write_vocab_csv(vocab_dir, "CONCEPT", mtime_offset=-120)
    context = build_sensor_context(cursor=cursor)
    result = omop_vocab_sensor(context)
    assert isinstance(result, SensorResult)
    assert result.run_requests is not None
    assert len(result.run_requests) == 1


def test_cursor_updates_correctly(vocab_dir):
    _write_vocab_csv(vocab_dir, "VOCABULARY")
    context = build_sensor_context()
    omop_vocab_sensor(context)
    assert context.cursor is not None
    cursor = json.loads(context.cursor)
    assert "vocabulary" in cursor
    assert isinstance(cursor["vocabulary"], float)
