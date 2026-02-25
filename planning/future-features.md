# Future Features

Acknowledged features that are out of current scope. Each item includes context on when it becomes relevant and what it would involve.

## Cloud storage for DuckLake

- **Azure Blob Storage**: Configure DuckDB's `azure` extension and point DuckLake's `DATA_PATH` to an Azure Blob container. Requires `azure-storage-blob` (already a dependency). Relevant when deploying to Azure or when data volumes exceed local disk.

- **S3 Storage**: Configure DuckDB's `httpfs` extension and point DuckLake's `DATA_PATH` to an S3 bucket. Relevant for AWS deployments.

## Large dataset writes via DuckDBPyRelation

Add `duckdb.DuckDBPyRelation` support in `handle_output` so assets can return a lazy DuckDB relation instead of a materialized `pl.DataFrame`. DuckDB writes the query result directly to DuckLake without entering Python memory, enabling writes of arbitrary size.

Implementation sketch:
```python
def handle_output(self, context, obj):
    if isinstance(obj, duckdb.DuckDBPyRelation):
        # Zero-copy: DuckDB writes from query plan, no Python RAM
        self._conn.execute(f"CREATE OR REPLACE TABLE {ref} AS SELECT * FROM obj")
    elif isinstance(obj, pl.DataFrame):
        # Current path: register + CTAS
        ...
```

Relevant when a pipeline step produces data too large to fit in Python memory (e.g., full joins across large tables). Until then, bounded ingestion and lazy reads keep data manageable. See ADR-004, Decision 4.

Estimated effort: ~2 hours (implementation + tests). Main unknown: verifying the exact DuckDB syntax for writing a Python-bound `DuckDBPyRelation` to a table.

## Observability

- **Prometheus metrics**: Add a `/metrics` endpoint using `prometheus-client` to
  FastAPI, scraped by a Prometheus server with Grafana dashboards. Relevant when
  multi-station deployments, historical uptime tracking, or automated alerting
  are needed. Until then, live service status is covered by the `/health`
  endpoint. See ADR-002 for context.

## Data integrity

- **Catalog consistency check**: A module that walks
  DuckLake's catalog tables and verifies every referenced Parquet file exists in storage. A *catalog file system consistency check (fsck)* for detecting drift when files are added, modified or deleted while the service is down.

- **Stale asset reconciliation**: Mark Dagster assets as stale when their
  backing DuckLake files are missing or corrupted. Integrates the catalog
  consistency check with Dagster's asset health system.

## Data formats

- **Binary files** (DICOM, NIfTI): Needs a file-reference pattern where the
  catalog stores metadata and a pointer to the binary in object storage.

- **ML artifacts** (pickle, safetensor): Same file-reference pattern as binary
  files, potentially with versioning support.
