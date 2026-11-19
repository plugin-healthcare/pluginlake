# DuckLake

## Resource limits

Every DuckDB connection gets the limits of `DuckDBLimitSettings` when it is opened:

| Variable | Default | Meaning |
|----------|---------|---------|
| `DUCKLAKE_MEMORY_LIMIT` | `2GB` | Memory per connection. Without a limit DuckDB takes 80% of the host memory. |
| `DUCKLAKE_TEMP_DIRECTORY` | `.data/tmp/duckdb` | Where a query spills to disk when it exceeds the memory limit (on the data volume in compose). Empty disables spilling. |
| `DUCKLAKE_MAX_TEMP_DIRECTORY_SIZE` | `10GB` | Disk space a connection may spill. |

Each connection is a separate DuckDB instance, so the limits apply per connection: the API shares one, and every Dagster run opens its own.
Some operations (for example `list()` aggregates) cannot spill and fail at the memory limit regardless of the disk limit.

A query beyond the limits raises `duckdb.OutOfMemoryException`.
The API answers it with HTTP 507 and a message that names the limits and the variables to raise; the IO manager turns it into `ResourceLimitError` with the table it was writing, which the Dagster UI shows on the failed run.
Polars work in an asset outside DuckDB is not covered by these limits.

## Setup

::: pluginlake.core.ducklake.setup

## IO Manager

::: pluginlake.core.ducklake.io_manager

## Settings

::: pluginlake.core.config
