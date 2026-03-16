# Future Features

Planned features that are out of current scope.

## Cloud storage for DuckLake

- **Azure Blob Storage**: configure DuckDB's `azure` extension to point DuckLake at an Azure Blob container
- **S3-compatible storage**: configure DuckDB's `httpfs` extension for any S3-compatible endpoint

## Large dataset writes

- **DuckDBPyRelation support**: allow assets to return a lazy DuckDB relation instead of a materialized `pl.DataFrame`, enabling zero-copy writes of arbitrary size

## Security

- **Fine-grained access control**: authentication and authorization at the transaction level (per-query, per-write)
- **Activity logging**: audit trail of all data access and mutations for compliance and debugging

## Observability

- **Prometheus metrics**: `/metrics` endpoint with Grafana dashboards for multi-station deployments and alerting

## Data integrity

- **Catalog consistency check**: verify every referenced Parquet file exists in storage (fsck for DuckLake)
- **Stale asset reconciliation**: mark Dagster assets as stale when backing files are missing or corrupted

## Data formats

- **Binary files** (DICOM, NIfTI): file-reference pattern with metadata in catalog, binary in object storage
- **ML artifacts** (pickle, safetensor): same pattern, potentially with versioning
