"""Shared query utilities for OMOP query modules."""

import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import date

import duckdb
import polars as pl

from pluginlake.core.ducklake.setup import setup_ducklake
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


class QueryError(Exception):
    """Raised when an OMOP query fails."""


@contextmanager
def ensure_connection(
    con: duckdb.DuckDBPyConnection | None,
) -> Generator[duckdb.DuckDBPyConnection]:
    """Yield an existing connection or create (and close) a new one."""
    should_close = con is None
    if con is None:
        con = setup_ducklake()
    try:
        yield con
    finally:
        if should_close:
            con.close()


def execute_query(
    con: duckdb.DuckDBPyConnection,
    query: str,
    params: list | dict | None,
    log_fn: Callable[[], None],
) -> pl.DataFrame:
    """Execute a query, log timing, and return a Polars DataFrame."""
    log_fn()
    start = time.perf_counter()
    try:
        result = con.execute(query, params) if params else con.execute(query)
        columns = [desc[0] for desc in result.description]
        df = pl.DataFrame(result.fetchall(), schema=columns, orient="row")
    except duckdb.CatalogException as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "Query failed: table or column not found",
            extra={"duration_ms": round(duration_ms, 2), "error": str(exc)},
        )
        raise QueryError(str(exc)) from exc
    except duckdb.BinderException as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "Query failed: invalid parameter or type",
            extra={"duration_ms": round(duration_ms, 2), "error": str(exc)},
        )
        raise QueryError(str(exc)) from exc
    except duckdb.Error as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "Query failed",
            extra={"duration_ms": round(duration_ms, 2), "error": str(exc)},
        )
        raise QueryError(str(exc)) from exc
    else:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Query completed",
            extra={"duration_ms": round(duration_ms, 2), "row_count": len(df)},
        )
        return df


def build_filter_query(
    table: str,
    conditions: list[str],
    params: list,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Build a parameterised SELECT query with optional ORDER BY and LIMIT."""
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"SELECT * FROM {table} WHERE {where_clause}"  # noqa: S608 — table/conditions from trusted internal callers

    if order_by:
        query += " ORDER BY " + order_by
    if limit:
        query += " LIMIT " + str(limit)

    return query, params


def add_filter(
    conditions: list[str],
    params: list,
    column: str,
    operator: str,
    value: int | date | str | None,
) -> None:
    """Append a condition and parameter value if the value is not None."""
    if value is not None:
        conditions.append(column + " " + operator + " ?")
        params.append(value)
