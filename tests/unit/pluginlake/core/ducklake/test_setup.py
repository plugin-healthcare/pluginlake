"""Tests for DuckLake setup and tuning options."""

from unittest.mock import MagicMock, call

from pluginlake.core.config import DuckLakeSettings
from pluginlake.core.ducklake.setup import _apply_tuning_options


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
        pg_password="test",  # noqa: S106
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
