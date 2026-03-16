# API

The pluginlake API is a FastAPI application that serves as the central endpoint for the data station.
It uses an app-factory pattern (`create_app()`) for clean initialisation and testability.

## Quick start

```bash
# Local
uv run python -m pluginlake

# Docker (dev)
just dev-up-headless
```

The server listens on `http://0.0.0.0:8000` by default.
Override with `PLUGINLAKE_SERVER_HOST` and `PLUGINLAKE_SERVER_PORT`.

## Endpoints

### Health

| Method | Path      | Description                               |
|--------|-----------|-------------------------------------------|
| GET    | `/health` | Liveness check, returns `{"status":"ok"}` |
| GET    | `/ready`  | Readiness check                           |

### Ingestion

| Method | Path                              | Description                                  |
|--------|-----------------------------------|----------------------------------------------|
| POST   | `/api/v1/ingest/{table_name}/csv` | Upload a CSV file for ingestion              |
| POST   | `/api/v1/omop/{table_name}/csv`   | Upload an OMOP CDM CSV file                  |
| POST   | `/api/v1/fhir/ndjson`             | Upload a FHIR NDJSON bundle                  |

### Catalog

| Method | Path                              | Description                              |
|--------|-----------------------------------|------------------------------------------|
| GET    | `/api/v1/catalog/schemas`         | List DuckLake schemas                    |
| GET    | `/api/v1/catalog/tables`          | List tables with column counts           |
| GET    | `/api/v1/catalog/columns`         | List columns for a table                 |
| GET    | `/api/v1/catalog/column-stats`    | Column-level statistics                  |
| GET    | `/api/v1/catalog/layer-summary`   | Table and row counts per schema/layer    |

### Orchestration

| Method | Path                   | Description                         |
|--------|------------------------|-------------------------------------|
| GET    | `/api/v1/assets`       | List registered Dagster assets      |
| GET    | `/api/v1/runs`         | List recent Dagster runs            |
| GET    | `/api/v1/runs/{id}`    | Get status of a specific run        |

### Statistics

| Method | Path                              | Description                          |
|--------|-----------------------------------|--------------------------------------|
| GET    | `/api/v1/omop/statistics`         | OMOP table-level statistics          |
| GET    | `/api/v1/fhir/statistics`         | FHIR resource-level statistics       |

## Middleware

Middleware is applied in the following order (outermost first):

1. **CORS**: allows all origins, methods, and headers. Tighten `allow_origins` before going to production.
2. **Request logging**: logs every request/response with method, path, status code, and duration (ms).

## Error handling

Three global exception handlers are registered:

| Exception           | Status code | Behaviour                                |
|---------------------|-------------|------------------------------------------|
| `PluginLakeError`   | custom      | Domain errors with a configurable status |
| `ValidationError`   | 422         | Pydantic validation failures             |
| Any other exception | 500         | Generic "Internal server error" response |

All errors are returned as JSON `{"detail": "..."}`.

## Authentication and authorisation

Auth is implemented as FastAPI dependency-injection placeholders that can be swapped out for real implementations later.

### AuthN: `require_auth`

A dependency that validates the current request and returns a `User` object.
The placeholder always returns an anonymous user.

```python
from pluginlake.api.security import CurrentUser

@router.get("/me")
async def me(user: CurrentUser) -> dict:
    return {"id": user.id, "name": user.name}
```

### AuthZ: `require_role`

A dependency factory that checks the user's roles.
The placeholder always passes.

```python
from fastapi import Depends
from pluginlake.api.security import require_role

@router.get("/admin", dependencies=[Depends(require_role("admin"))])
def admin_panel():
    return {"access": "granted"}
```

### Switching to real auth

1. Replace `require_auth` with real token validation (e.g. OAuth2 bearer / JWT).
2. Replace `require_role._check_role` with actual role enforcement, raising `HTTPException(403)` on failure.
3. Update the `User` model to include any additional fields your identity provider returns.

## Configuration

The API uses the following settings classes from `pluginlake.config`:

| Class            | Env prefix              | Purpose                |
|------------------|-------------------------|------------------------|
| `Settings`       | `PLUGINLAKE_`           | Debug, log level       |
| `ServerSettings` | `PLUGINLAKE_SERVER_`    | Host, port             |
| `StorageSettings`| `PLUGINLAKE_STORAGE_`   | Data directory, layers |

See the [Configuration reference](config.md) for full details.

## Project structure

```
src/pluginlake/api/
├── __init__.py
├── app.py              # App factory (create_app)
├── config.py           # API-specific config
├── endpoints.py        # Legacy compat
├── exceptions.py       # Global exception handlers + PluginLakeError
├── middleware.py        # RequestLoggingMiddleware
├── security.py         # Auth placeholders (require_auth, require_role)
├── routers/
│   ├── __init__.py
│   ├── assets.py       # /api/v1/assets, /api/v1/runs
│   ├── catalog.py      # /api/v1/catalog/*
│   ├── fhir.py         # /api/v1/fhir/ndjson
│   ├── fhir_statistics.py  # /api/v1/fhir/statistics
│   ├── health.py       # /health, /ready
│   ├── ingest.py       # /api/v1/ingest
│   ├── omop.py         # /api/v1/omop
│   └── omop_statistics.py  # /api/v1/omop/statistics
└── services/
    ├── __init__.py
    ├── fhir_ingestion.py
    ├── ingestion.py
    └── omop_ingestion.py
```
