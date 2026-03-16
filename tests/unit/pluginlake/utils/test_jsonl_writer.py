"""Tests for pluginlake.utils.jsonl_writer."""

import json
from pathlib import Path
from unittest.mock import patch

from pluginlake.utils.jsonl_writer import (
    append_jsonl,
    write_ingestion_log,
    write_query_log,
)


def _read_jsonl(directory: Path) -> list[dict]:
    files = sorted(directory.glob("*.jsonl"))
    lines: list[dict] = []
    for f in files:
        lines.extend(json.loads(line) for line in f.read_text().strip().splitlines())
    return lines


def test_append_jsonl_creates_file(tmp_path: Path):
    append_jsonl(tmp_path / "logs", {"key": "value"})
    entries = _read_jsonl(tmp_path / "logs")
    assert len(entries) == 1
    assert entries[0]["key"] == "value"


def test_append_jsonl_appends_multiple(tmp_path: Path):
    log_dir = tmp_path / "logs"
    append_jsonl(log_dir, {"n": 1})
    append_jsonl(log_dir, {"n": 2})
    entries = _read_jsonl(log_dir)
    assert len(entries) == 2
    assert entries[0]["n"] == 1
    assert entries[1]["n"] == 2


def test_append_jsonl_handles_oserror(tmp_path: Path):
    log_dir = tmp_path / "logs"
    with patch("pluginlake.utils.jsonl_writer.Path.mkdir", side_effect=OSError("disk full")):
        append_jsonl(log_dir, {"key": "value"})
    assert not log_dir.exists()


def test_write_query_log_structure(tmp_path: Path):
    log_dir = tmp_path / "query"
    write_query_log(
        log_dir,
        method="GET",
        path="/api/v1/health",
        query_params="",
        status_code=200,
        duration_ms=12.345,
        client_ip="127.0.0.1",
        user_agent="test-agent",
    )
    entries = _read_jsonl(log_dir)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["method"] == "GET"
    assert entry["path"] == "/api/v1/health"
    assert entry["query_params"] == ""
    assert entry["status_code"] == 200
    assert entry["duration_ms"] == 12.35
    assert entry["client_ip"] == "127.0.0.1"
    assert entry["user_agent"] == "test-agent"
    assert "timestamp" in entry


def test_write_ingestion_log_structure(tmp_path: Path):
    log_dir = tmp_path / "ingestion"
    write_ingestion_log(
        log_dir,
        file_id="abc123",
        filename="data.csv",
        dataset="patients",
        size_bytes=1024,
        status="completed",
        dagster_run_id="run-xyz",
    )
    entries = _read_jsonl(log_dir)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["file_id"] == "abc123"
    assert entry["filename"] == "data.csv"
    assert entry["dataset"] == "patients"
    assert entry["size_bytes"] == 1024
    assert entry["status"] == "completed"
    assert entry["dagster_run_id"] == "run-xyz"
    assert entry["error"] is None
    assert "timestamp" in entry
