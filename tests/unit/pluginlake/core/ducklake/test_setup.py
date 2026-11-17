"""Tests for DuckLake setup and tuning options."""

from pathlib import Path
from unittest.mock import MagicMock, call

import duckdb
import pytest
from pydantic import SecretStr, ValidationError

from pluginlake.core.config import DuckDBLimitSettings, DuckLakeSettings
from pluginlake.core.ducklake.setup import _apply_tuning_options, apply_resource_limits, limit_exceeded_message


def _make_settings(
    *,
    target_file_size: int | None = None,
    parquet_compression: str | None = None,
    per_thread_output: bool | None = None,
) -> DuckLakeSettings:
    return DuckLakeSettings(
        pg_host="localhost",
        pg_port=5432,
        pg_user="test",
        pg_password=SecretStr("test"),
        pg_db="testdb",
        target_file_size=target_file_size,
        parquet_compression=parquet_compression,
        per_thread_output=per_thread_output,
    )


def test_tuning_fields_default_to_none():
    settings = _make_settings()
    assert settings.target_file_size is None
    assert settings.parquet_compression is None
    assert settings.per_thread_output is None


def test_tuning_fields_accept_values():
    settings = _make_settings(
        target_file_size=268435456,
        parquet_compression="zstd",
        per_thread_output=True,
    )
    assert settings.target_file_size == 268435456
    assert settings.parquet_compression == "zstd"
    assert settings.per_thread_output is True


def test_apply_tuning_no_options():
    conn = MagicMock()
    settings = _make_settings()
    _apply_tuning_options(conn, settings)
    conn.execute.assert_not_called()


def test_apply_tuning_all_options():
    conn = MagicMock()
    settings = _make_settings(
        target_file_size=268435456,
        parquet_compression="zstd",
        per_thread_output=True,
    )
    _apply_tuning_options(conn, settings)
    conn.execute.assert_has_calls(
        [
            call("CALL ducklake_set_option('ducklake', 'target_file_size', 268435456)"),
            call("CALL ducklake_set_option('ducklake', 'parquet_compression', 'zstd')"),
            call("CALL ducklake_set_option('ducklake', 'per_thread_output', true)"),
        ]
    )


def test_apply_tuning_partial_options():
    conn = MagicMock()
    settings = _make_settings(parquet_compression="snappy")
    _apply_tuning_options(conn, settings)
    assert conn.execute.call_count == 1
    conn.execute.assert_called_once_with("CALL ducklake_set_option('ducklake', 'parquet_compression', 'snappy')")


def test_apply_tuning_per_thread_output_false():
    conn = MagicMock()
    settings = _make_settings(per_thread_output=False)
    _apply_tuning_options(conn, settings)
    conn.execute.assert_called_once_with("CALL ducklake_set_option('ducklake', 'per_thread_output', false)")


# --- resource limits ---


def _setting(conn: duckdb.DuckDBPyConnection, name: str) -> str:
    row = conn.execute(f"SELECT current_setting('{name}')").fetchone()
    assert row is not None
    return row[0]


def test_resource_limit_defaults(monkeypatch: pytest.MonkeyPatch):
    for name in ("MEMORY_LIMIT", "TEMP_DIRECTORY", "MAX_TEMP_DIRECTORY_SIZE"):
        monkeypatch.delenv(f"DUCKLAKE_{name}", raising=False)
    limits = DuckDBLimitSettings()
    assert (limits.memory_limit, limits.max_temp_directory_size) == ("2GB", "10GB")
    assert limits.temp_directory == ".data/tmp/duckdb"


def test_apply_resource_limits_sets_limits_and_creates_spill_dir(tmp_path: Path):
    spill = tmp_path / "a" / "b"
    conn = duckdb.connect()
    apply_resource_limits(conn, DuckDBLimitSettings(memory_limit="256MB", temp_directory=str(spill)))
    assert spill.is_dir()
    assert _setting(conn, "temp_directory") == str(spill)
    assert _setting(conn, "max_temp_directory_size") == "9.3 GiB"  # 10GB
    assert _setting(conn, "memory_limit") == "244.1 MiB"


def test_query_beyond_limits_fails_with_out_of_memory(tmp_path: Path):
    conn = duckdb.connect()
    apply_resource_limits(
        conn,
        DuckDBLimitSettings(memory_limit="32MB", temp_directory=str(tmp_path), max_temp_directory_size="1MB"),
    )
    with pytest.raises(duckdb.OutOfMemoryException):
        conn.execute("SELECT i % 100000 AS g, list(i) FROM range(5000000) t(i) GROUP BY g").fetchall()


@pytest.mark.parametrize(
    ("field", "value"),
    [("memory_limit", "2 bananas"), ("max_temp_directory_size", "10GB'; DROP"), ("temp_directory", "spill/x'y")],
)
def test_resource_limits_reject_unsafe_values(field: str, value: str):
    with pytest.raises(ValidationError):
        DuckDBLimitSettings.model_validate({field: value})


def test_limit_message_without_spilling():
    message = limit_exceeded_message(DuckDBLimitSettings(memory_limit="1GB", temp_directory=""))
    assert "1GB of memory" in message
    assert "spilling is disabled" in message
