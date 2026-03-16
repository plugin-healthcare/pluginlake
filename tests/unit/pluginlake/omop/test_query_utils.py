"""Tests for shared query utilities."""

import logging
from unittest.mock import MagicMock, patch

import duckdb
import polars as pl
import pytest

from pluginlake.omop.query_utils import QueryError, ensure_connection, execute_query


@pytest.fixture
def mem_db():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE test_table (id INTEGER, name VARCHAR)")
    con.execute("INSERT INTO test_table VALUES (1, 'Alice'), (2, 'Bob')")
    yield con
    con.close()


def test_execute_query_logs_duration_and_row_count(mem_db, caplog):
    with caplog.at_level(logging.INFO, logger="pluginlake.omop.query_utils"):
        result = execute_query(
            mem_db,
            "SELECT * FROM test_table",
            None,
            lambda: None,
        )

    assert len(result) == 2
    assert "Query completed" in caplog.text


def test_execute_query_logs_error_on_missing_table(mem_db, caplog):
    with (
        caplog.at_level(logging.ERROR, logger="pluginlake.omop.query_utils"),
        pytest.raises(QueryError, match="nonexistent_table"),
    ):
        execute_query(
            mem_db,
            "SELECT * FROM nonexistent_table",
            None,
            lambda: None,
        )

    assert "Query failed" in caplog.text


def test_execute_query_logs_error_on_bad_params(mem_db, caplog):
    with (
        caplog.at_level(logging.ERROR, logger="pluginlake.omop.query_utils"),
        pytest.raises(QueryError),
    ):
        execute_query(
            mem_db,
            "SELECT * FROM test_table WHERE id = $bad_param",
            {"wrong_param": 1},
            lambda: None,
        )

    assert "Query failed" in caplog.text


def test_execute_query_empty_result(mem_db):
    result = execute_query(
        mem_db,
        "SELECT * FROM test_table WHERE id = ?",
        [999],
        lambda: None,
    )

    assert isinstance(result, pl.DataFrame)
    assert len(result) == 0
    assert "id" in result.columns
    assert "name" in result.columns


def test_ensure_connection_closes_when_created():
    mock_con = MagicMock(spec=duckdb.DuckDBPyConnection)

    with (
        patch("pluginlake.omop.query_utils.setup_ducklake", return_value=mock_con),
        ensure_connection(None) as conn,
    ):
        assert conn is mock_con

    mock_con.close.assert_called_once()


def test_ensure_connection_keeps_external():
    mock_con = MagicMock(spec=duckdb.DuckDBPyConnection)

    with ensure_connection(mock_con) as conn:
        assert conn is mock_con

    mock_con.close.assert_not_called()
