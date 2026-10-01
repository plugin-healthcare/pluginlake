# Reference

Auto-generated Python library documentation.
Each page is built from source code docstrings using mkdocstrings.

## API

| Page | Description |
|------|-------------|
| [API Overview](api.md) | REST API endpoints, middleware, authentication, and configuration. |
| [API Specification](api-specification.md) | Interactive OpenAPI specification (Swagger UI). |

## Core Library

| Module | Description |
|--------|-------------|
| [Configuration](config.md) | Root settings, environment variables, and Pydantic models. |
| [DuckLake](ducklake.md) | Catalog setup, connection management, and IO manager. |
| [Storage](storage.md) | Data persistence layer and file handling. |
| [Ingestion](ingestion.md) | Generic ingestion service and validation pipeline. |
| [Utilities](utils.md) | Shared helpers: logging, formatting, and common functions. |

Domain modules (OMOP, FHIR, and other clinical models) are not part of core.
They live in project packages that plug into a node via the
`pluginlake.projects` entry point (ADR-009) and are documented in each project's
own reference docs.
