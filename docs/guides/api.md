# API

The pluginlake API is a FastAPI application that serves as the central endpoint for the data station.
It uses an app-factory pattern (`create_app()`) for clean initialisation and testability.

## Quick start

```bash
# Local
uv run python -m pluginlake

# Docker (dev)
cd deploy/compose && docker compose -f docker-compose.dev.yaml up pluginlake
```

The server listens on `http://0.0.0.0:8000` by default.
Override with `PLUGINLAKE_SERVER_HOST` and `PLUGINLAKE_SERVER_PORT`.

## Endpoints

| Method | Path      | Description                               |
|--------|-----------|-------------------------------------------|
| GET    | `/health` | Liveness check, returns `{"status":"ok"}` |
| GET    | `/ready`  | Readiness check                           |

## Middleware

Middleware is applied in the following order (outermost first):

1. **CORS** — allows all origins, methods, and headers. Tighten `allow_origins` before going to production.
2. **Request logging** — logs every request/response with method, path, status code, and duration (ms).

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

See the [Configuration guide](configuration.md) for full details.

## Project structure

```
src/pluginlake/api/
├── __init__.py
├── app.py            # App factory (create_app)
├── config.py         # API-specific config (reserved)
├── endpoints.py      # Legacy compat (empty)
├── exceptions.py     # Global exception handlers + PluginLakeError
├── middleware.py      # RequestLoggingMiddleware
├── security.py       # Auth placeholders (require_auth, require_role)
└── routers/
    ├── __init__.py
    └── health.py     # /health, /ready endpoints
```
