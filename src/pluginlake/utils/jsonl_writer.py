"""JSONL operational log writer.

Appends structured JSON entries to date-partitioned JSONL files for
query traffic and ingestion history logging (ADR-003).
"""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(directory: Path) -> threading.Lock:
    key = str(directory)
    with _locks_lock:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def append_jsonl(directory: Path, entry: dict) -> None:
    """Append a single JSON entry as one line to a date-partitioned JSONL file."""
    now = datetime.now(UTC)
    filename = now.strftime("%Y-%m-%d") + ".jsonl"
    lock = _get_lock(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with lock, (directory / filename).open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        logger.warning("Failed to write JSONL entry to %s", directory / filename, exc_info=True)


def write_query_log(  # noqa: PLR0913 — all fields are keyword-only; a wrapper dataclass adds indirection without benefit
    log_dir: Path,
    *,
    method: str,
    path: str,
    query_params: str,
    status_code: int,
    duration_ms: float,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    """Write an API request/response entry to the query log."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "method": method,
        "path": path,
        "query_params": query_params,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "client_ip": client_ip,
        "user_agent": user_agent,
    }
    append_jsonl(log_dir, entry)


def write_ingestion_log(  # noqa: PLR0913 — all fields are keyword-only; a wrapper dataclass adds indirection without benefit
    log_dir: Path,
    *,
    file_id: str,
    filename: str,
    dataset: str,
    size_bytes: int,
    status: str,
    dagster_run_id: str | None,
    error: str | None = None,
) -> None:
    """Write a file ingestion outcome entry to the ingestion log."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "file_id": file_id,
        "filename": filename,
        "dataset": dataset,
        "size_bytes": size_bytes,
        "status": status,
        "dagster_run_id": dagster_run_id,
        "error": error,
    }
    append_jsonl(log_dir, entry)
