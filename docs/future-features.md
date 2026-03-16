# Future Features

Acknowledged features that are out of current scope. Each item includes context on when it becomes relevant and what it would involve.

## Storage backends

- **Azure Blob Storage**: Add an `AzureBlobStorageBackend` that implements
  `StorageBackend`. Requires `azure-storage-blob` (already a dependency) and
  DuckDB's `azure` extension for `configure_duckdb()`. Relevant when deploying
  to Azure or when data volumes exceed local disk.

- **S3 Storage**: Add an `S3StorageBackend` using DuckDB's `httpfs` extension.
  Relevant for AWS deployments.

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
