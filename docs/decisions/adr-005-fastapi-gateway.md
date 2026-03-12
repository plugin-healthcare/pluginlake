# ADR-005: FastAPI as unified API gateway

**Status:** Proposed
**Date:** 2026-03-05

## Context

pluginlake needs to support multiple client types (web UI, CLI, external integrations, other pluginlake stations) while maintaining centralized authentication, authorization, and audit logging.
Dagster OSS does not provide built-in auth or a data-serving API.
We plan to build a custom portal UI and eventually run Dagster in headless mode.

## Decision

Use FastAPI as the single entry point for all external access to a pluginlake instance.
All clients (UI, CLI, external systems) interact exclusively through the FastAPI API.
No downstream service (Dagster, DuckLake, storage) is exposed directly.

FastAPI auto-generates an OpenAPI specification from the endpoint definitions.
This gives us a machine-readable API contract that can be used to generate client SDKs, keep documentation in sync, and validate requests and responses, all without maintaining a separate spec file.

## Architecture

```
┌─────────┐  ┌─────────┐  ┌─────────────┐
│  Web UI │  │   CLI   │  │External svc  │
└────┬────┘  └────┬────┘  └──────┬───────┘
     │            │              │
     └────────────┼──────────────┘
                  │
          ┌───────▼────────┐
          │    FastAPI      │
          │  (authN/authZ   │
          │   audit, rate   │
          │   limiting)     │
          └───┬───┬───┬────┘
              │   │   │
     ┌────────┘   │   └────────┐
     ▼            ▼            ▼
  DuckLake    Dagster       Audit log
  (catalog    (orchestration (JSONL)
   + data)    via GraphQL)
```

## API surface

Example API endpoints:

| Domain | Endpoint | Purpose |
|---|---|---|
| Catalog | `GET /api/catalog/schemas` | List DuckLake schemas |
| Catalog | `GET /api/catalog/tables` | List tables |
| Catalog | `GET /api/catalog/tables/{schema}/{table}` | Query table data |
| Orchestration | `GET /api/runs` | List Dagster runs |
| Orchestration | `GET /api/runs/{id}` | Run status and logs |
| Orchestration | `POST /api/assets/{key}/materialize` | Trigger asset materialization |
| Orchestration | `GET /api/assets` | List registered assets |
| Lineage | `GET /api/assets/{key}/lineage` | Asset-level dependency graph |
| Lineage | `GET /api/assets/{key}/lineage/columns` | Column-level lineage for an asset |
| System | `GET /health` | Health check (no auth) |
| Docs | `GET /docs` | Interactive OpenAPI documentation (Swagger UI) |
| Docs | `GET /openapi.json` | Machine-readable OpenAPI spec |

## Why FastAPI gateway over exposing Dagster directly

| Concern | Dagster UI direct | FastAPI gateway |
|---|---|---|
| Authentication | None in OSS | Centralized (API key, OAuth, etc.) |
| Authorization | None in OSS | Role-based, per-endpoint |
| CLI / scripting access | Requires Dagster CLI + gRPC | Any HTTP client |
| Data serving | Not supported | DuckLake reads with auth |
| Audit logging | Limited | Full control via middleware |
| Rate limiting | None | Standard middleware |
| Multi-station federation | Each station exposes own UI | Uniform API contract across stations |
| API documentation | None | Auto-generated OpenAPI spec, interactive Swagger UI |

## Rollout phases

1. **Gateway API:** Build `src/pluginlake/api/` with catalog browsing, health, and API key auth. Dagster UI remains available for development.
2. **Orchestration proxy:** Add Dagster GraphQL proxy endpoints (runs, materialization, schedules).
3. **Client layer:** Build UI and/or CLI that consume only `/api/*`. Frontend choice (SPA, Streamlit, TUI) is a pure presentation concern. Client SDKs can be generated from the OpenAPI spec.
4. **Headless Dagster:** Remove `dagster-webserver` from production. Keep only `dagster-daemon` + `dagster-code-server`. The FastAPI service is the sole user-facing entry point.

## Consequences

- One auth boundary to maintain, not per-service.
- UI and CLI are thin clients with no direct database or orchestrator access.
- Adding new clients (mobile, partner integrations) requires zero backend changes.
- Dagster becomes an internal implementation detail, replaceable without breaking consumers.
- OpenAPI spec is always in sync with the code, so documentation and client SDKs never drift.
- Adds one service to deploy and monitor (acceptable given it already exists in the stack).
