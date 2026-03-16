# Release Notes

## v0.1.0 — Initial Release

*2026-03-16*

First public release of pluginlake.

### Highlights

- **DuckLake-backed data catalog**: OMOP data stored as Parquet with PostgreSQL catalog metadata, providing schema tracking and versioning out of the box.
- **Dagster orchestration**: asset-based pipelines with a custom DuckLake I/O manager for automated catalog integration.
- **FHIR ingestion**: load FHIR resources into the OMOP CDM.
- **FastAPI data access layer**: REST API for querying and ingesting data.
- **Datastation dashboard**: Streamlit UI for browsing the data catalog.
- **Docker Compose setup**: containerized dev and prod environments (Dagster + PostgreSQL + FastAPI).
- **Azure infrastructure**: OpenTofu modules for Azure deployment with Azure AD authentication.
- **Documentation site**: Zensical-based docs with architecture decision records, guides, and API reference, deployed via GitHub Pages.
- **CI/CD**: GitHub Actions for linting, testing, and docs deployment.
- **OMOP vocabulary support**: load and query OMOP vocabularies.

### Stack

- Python 3.13+, managed with [uv](https://docs.astral.sh/uv/)
- DuckLake, Dagster, PostgreSQL
- FastAPI, Polars, Streamlit
- Docker Compose, OpenTofu, GitHub Actions
