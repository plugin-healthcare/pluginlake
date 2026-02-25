# ADR-002: DuckLake integration with Dagster + logging strategy

- **Status:** Proposed
- **Date:** 2026-02-23
- **Authors:** Yannick Vinkesteijn

## Context

pluginlake uses DuckLake as its data catalog and Dagster for orchestration. This ADR covers how they work together: how assets are persisted, what data formats are supported, how data flows in and out via the API, and how operational concerns (logging, monitoring, resilience) are handled.

## Principles

1. **DuckLake is the single source of truth.** Every data asset goes through DuckLake. No asset may bypass the catalog. If a format isn't supported, an IO manager extension needs to be implemented.
2. **Dagster orchestrates all writes.** Data only enters DuckLake through Dagster-managed pipelines. This ensures both lineage and catalog registration.
3. **Extend, don't bypass.** When new data formats are needed, the IO manager is extended with new type handlers.

---

## Decision 1: Asset persistence

**All Dagster assets are persisted via a custom DuckLake IO manager.**

Assets return data and the IO manager handles storage and catalog registration. Asset code contains no storage logic for data that is persisted. The IO manager maps asset keys to DuckLake schemas and tables automatically.

```python
@asset(key_prefix="omop")
def condition_era(raw_conditions: pl.DataFrame) -> pl.DataFrame:
    return raw_conditions.filter(...)
    # → IO manager writes to DuckLake table: omop.condition_era
```

### Scope

The IO manager handles the following formats:

| Format                                              | Stored as                                           |
|-----------------------------------------------------|-----------------------------------------------------|
| Tabular data (CSV, Parquet, any source to columnar) | DuckLake table (Parquet-backed)                     |
| JSON / XML documents                                | DuckLake table with JSON or text column             |

DuckLake supports `json`, `struct`, `list`, and `map` column types natively, so deeply nested and polymorphic documents can be stored without flattening. Every asset output goes through the IO manager, which registers it in the DuckLake catalog and writes the data. If the data has not changed, the IO manager skips the write and no new version is created. Domain-specific transformations (e.g., FHIR to OMOP) are handled by Dagster assets and the IO manager persists and catalogs any new or updated assets.

For the initial scope of pluginlake, we focus on the following clinical data formats:

- **FHIR**: bundles and resources are stored as JSON columns. Dagster assets then extract, flatten, and map them to OMOP-compatible tabular form.
- **OMOP**: tabular by definition. Assets produce Polars DataFrames that the IO manager writes directly as Parquet-backed DuckLake tables.

> **Out of scope** acknowledged for future work, not implemented now:
>
>| Format       | Example            | Notes                                        |
>|--------------|--------------------|----------------------------------------------|
>| Binary files | DICOM, NIfTI       | Needs file-reference pattern/object storage. |
>| ML artifacts | pickle, safetensor | Needs file-reference pattern/object storage. |

### Why not a Dagster resource instead?

A resource requires every asset to explicitly call `ducklake.write(...)`. This is error-prone due to the possibility of a developer forgetting the call, which means data exists in the pipeline but not in the catalog. The IO manager guarantees catalog registration by design.

---

## Decision 2: Data ingestion and serving

### Ingestion: two-phase validation

Fast synchronous validation for immediate user feedback, asynchronous Dagster processing for business rules and persistence.

```
POST /ingest
  │
  ├─ Phase 1 (sync, fast feedback)
  │   ├─ Auth, rate limits, schema validation, basic quality checks
  │   ├─ FAIL → 422 with validation errors
  │   └─ PASS → write to staging, trigger Dagster run
  │             return 202 + tracking_id (= Dagster run_id)
  │
  └─ Phase 2 (async, Dagster)
      ├─ Business rule validation, quality scoring, transform
      ├─ FAIL → run failed in Dagster UI, queryable via tracking_id
      └─ PASS → data in DuckLake catalog
```

**Ingestion status** uses Dagster directly, the tracking ID is the Dagster run ID. No separate status table or database:

```
GET /ingest/{tracking_id}/status
  → queries Dagster GraphQL API → returns run state
```

This automatically extends to estimated completion times based on historical run statistics. FastAPI wrapper for Dagster GraphQL keeps the API consistent and ability to use same middleware as for other requests.

### Serving: direct DuckLake reads

```
GET /data/omop/condition_era?limit=100
  → FastAPI reads from DuckLake → returns data
```

Dagster is not in the read path because reads don't mutate data and routing through Dagster would add seconds of latency. We do implement a connection log to track data access patterns.

### Alternatives considered

| Approach                                                    | Rejected because                                                                              |
|-------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| Synchronous (FastAPI validates + writes + notifies Dagster) | User waits for full pipeline. Dagster only gets a notification, not lineage                   |
| Landing zone (FastAPI → staging → Dagster)                  | Adds complexity and decouples ingestion from processing. Staging area needed for raw payloads |

---

## Decision 3: Observability and logging

DuckLake is for data, not operations. Logs live outside the catalog.

| What | Where | Queryable via |
|------|-------|--------------|
| Application logs | stderr → container log driver | Docker/k8s log tooling |
| Traffic/audit logs | `.data/logs/query_log/YYYY-MM-DD.jsonl` | DuckDB `read_json()`, `cat`/`jq`, API |
| Ingestion history | `.data/logs/ingestion_log/YYYY-MM-DD.jsonl` | DuckDB `read_json()`, `cat`/`jq`, API |
| Ingestion status | Dagster PostgreSQL (run state) | Dagster GraphQL, `/ingest/{id}/status` |
| System health | `/health` endpoint | HTTP |

**Why JSONL files for logs?**

- Python logging module can write structured logs to JSONL files.
- No database or catalog overhead (no versioning, no schema tracking)
- Accessible when any of the services such as DuckLake or Postgres is down (`cat`, `grep`, `jq`)
- DuckDB reads them natively for serving via API or ad-hoc analysis.
- Easy lifecycle management with rotation and retention policies managed by dagster/duckdb.
- no extra infrastructure or services needed for logging and log storage

> **Out of scope (future work):** Prometheus metrics (a `/metrics` endpoint and Prometheus server + Grafana) are not included in the current setup. When multi-station deployments, historical uptime tracking, or automated alerting are needed, a `/metrics` endpoint using `prometheus-client` can be added to FastAPI and scraped by a Prometheus server. Until then, live service status is covered by the `/health` endpoint.

**Health endpoint**

The `/health` endpoint provides a quick snapshot of the system's health, checking connectivity to available services and other operational components. Each container/service exposes its own health status, and the endpoint aggregates these into a single response.

```json
GET /health → {"status": "ok|degraded", "components": {"postgres": "ok", "ducklake": "ok", "dagster": "ok"}}
```

The same health checks can be used by other services or an external monitoring system to track uptime and trigger alerts if any component is down.

### Resilience

| Component down | Data serving | Ingestion | Logs | Dagster UI |
|---------------|-------------|-----------|------|------------|
| PostgreSQL | No | No | Yes | No |
| DuckLake | No | Phase 1 works (staging) | Yes | Yes |
| Dagster | Yes | Phase 1 works (no processing) | Yes | No |
| FastAPI | No API | No API | Files on disk | Yes |

JSONL files on disk are the most resilient layer, accessible even when everything else is down.

---

## Infrastructure

```
PostgreSQL container
  ├─ dagster DB    → run state, schedules, events
  └─ ducklake DB   → catalog metadata (schemas, tables, versions)

Filesystem
  ├─ .data/lakehouse/   → Parquet files (DuckLake-managed)
  ├─ .data/staging/     → raw ingestion payloads awaiting Dagster
  └─ .data/logs/        → JSONL operational logs
```

## Responsibility split

| Concern | Owner | Mechanism |
|---------|-------|-----------|
| Orchestration (schedules, sensors, jobs) | Dagster | Jobs, sensors, schedules |
| Data transformations | Dagster | Asset functions |
| Data persistence and catalog | Dagster | DuckLake IO manager |
| Input validation (schema, format) | FastAPI | Pydantic models, middleware |
| Business validation (rules, quality) | Dagster | Asset functions |
| Ingestion status | Dagster | Run state via GraphQL |
| Data serving | FastAPI | Direct DuckLake reads |
| Health checks | FastAPI | `/health` endpoint |
| Operational logs (traffic, audit, ingestion) | FastAPI | JSONL files on disk |
| Application logs | All services | Python logging to stderr |

## Consequences

- Every data asset is registered and persisted through DuckLake. There are no alternative storage paths.
- The current scope covers tabular data, JSON/XML, and FHIR bundles. Binary files and ML artifacts are deferred to future work.
- Supporting new data formats requires extending the IO manager, not bypassing it.
- The ingestion tracking ID is the Dagster run ID, so no separate status infrastructure is needed.
- Operational logs are stored as JSONL files outside of DuckLake. They can be queried via DuckDB when needed.
- Prometheus metrics and alerting are out of scope. Live service status is provided by the `/health` endpoint.
- Stations stay lightweight with no message broker and no extra databases beyond PostgreSQL.
- The PostgreSQL init script creates both the `dagster` and `ducklake` databases in a single container.
