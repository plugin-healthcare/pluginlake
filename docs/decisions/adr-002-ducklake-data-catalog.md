# ADR-002: DuckLake integration with Dagster

- **Status:** Accepted?
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

Assets return data; the IO manager handles storage. Asset code contains no storage logic. The IO manager maps asset keys to DuckLake schemas and tables automatically.

```python
@asset(key_prefix="omop")
def condition_era(raw_conditions: pl.DataFrame) -> pl.DataFrame:
    return raw_conditions.filter(...)
    # → IO manager writes to DuckLake table: omop.condition_era
```

### Scope

**In scope** — the IO manager handles these formats:

| Format | Stored as |
|--------|-----------|
| Tabular data (CSV, Parquet, any source → standard columnar format) | DuckLake table (Parquet-backed) |
| JSON / XML documents | DuckLake table (JSON/text column or parsed to tabular) |

**Out of scope** — acknowledged for future work, not implemented now:

| Format | Example | Notes |
|--------|---------|-------|
| Binary files | DICOM, NIfTI | Needs file-reference pattern. Not needed for OMOP |
| ML artifacts | pickle, ONNX | Not a lakehouse concern at this stage |
| Raw FHIR bundles | Deeply nested JSON | Will be flattened to tabular when FHIR support is added |

### Why not a Dagster resource instead?

A resource requires every asset to explicitly call `ducklake.write(...)`. This is error-prone — a developer forgetting the call means data exists in the pipeline but not in the catalog. The IO manager guarantees catalog registration by design.

### Schema mapping

| Dagster asset key | DuckLake schema | DuckLake table |
|-------------------|----------------|----------------|
| `["titanic_raw"]` | `main` | `titanic_raw` |
| `["omop", "condition_era"]` | `omop` | `condition_era` |
| `["fhir", "patient"]` | `fhir` | `patient` |

- **Single-part key** → schema `main`, table = key name.
- **Multi-part key** → first part = schema, last part = table name.
- Schemas map 1:1 to data model modules (`pluginlake.definitions.omop` → `omop` schema).

---

## Decision 2: Data ingestion and serving

### Ingestion: two-phase validation

Fast synchronous validation for immediate user feedback, asynchronous Dagster processing for business rules and persistence.

```
POST /ingest
  │
  ├─ Phase 1 (sync, ~50-200ms)
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

**Ingestion status** uses Dagster directly — the tracking ID is the Dagster run ID. No separate status table or database:

```
GET /ingest/{tracking_id}/status
  → queries Dagster GraphQL API → returns run state
```

This naturally extends to estimated completion times based on historical run statistics.

### Serving: direct DuckLake reads

```
GET /data/omop/condition_era?limit=100
  → FastAPI reads from DuckLake → returns data
```

Dagster is not in the read path — reads don't mutate data and routing through Dagster would add seconds of latency.

### Alternatives considered

| Approach | Rejected because |
|----------|-----------------|
| Synchronous (FastAPI validates + writes + notifies Dagster) | User waits for full pipeline. Dagster only gets a notification, not lineage |
| Queue-based (FastAPI → message broker → Dagster) | Adds a message broker. Overkill for current scale |

---

## Decision 3: Observability and logging

DuckLake is for data, not operations. Logs live outside the catalog.

| What | Where | Queryable via |
|------|-------|--------------|
| Application logs | stderr → container log driver | Docker/k8s log tooling |
| Traffic/audit logs | `.data/logs/query_log/YYYY-MM-DD.jsonl` | DuckDB `read_json()`, `cat`/`jq`, API |
| Ingestion history | `.data/logs/ingestion_log/YYYY-MM-DD.jsonl` | DuckDB `read_json()`, `cat`/`jq`, API |
| Ingestion status | Dagster PostgreSQL (run state) | Dagster GraphQL, `/ingest/{id}/status` |
| Metrics | In-memory `/metrics` endpoint | Prometheus scrape |
| System health | `/health` endpoint | HTTP |

**Why JSONL files for logs?**
- No catalog overhead (no versioning, no schema tracking)
- Accessible when DuckLake or Postgres is down (`cat`, `grep`, `jq`)
- DuckDB reads them natively for SQL queries when needed
- Easy lifecycle — rotate or delete old files

**Prometheus metrics** are exposed via `/metrics` on the FastAPI service. No Prometheus server runs in the station — central infrastructure scrapes the endpoint.

**Health endpoint** reports per-component status:

```json
GET /health → {"status": "ok|degraded", "components": {"postgres": "ok", "ducklake": "ok", "dagster": "ok"}}
```

### Resilience

| Component down | Data serving | Ingestion | Logs | Dagster UI |
|---------------|-------------|-----------|------|-----------|
| PostgreSQL | No | No | Yes | No |
| DuckLake | No | Phase 1 works (staging) | Yes | Yes |
| Dagster | Yes | Phase 1 works (no processing) | Yes | No |
| FastAPI | No API | No API | Files on disk | Yes |

JSONL files on disk are the most resilient layer — accessible even when everything else is down.

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

| Concern | Owner |
|---------|-------|
| Orchestration (schedules, sensors, jobs) | Dagster |
| Data transformations | Dagster assets |
| Data persistence and catalog | DuckLake IO manager |
| Input validation (schema, format) | FastAPI |
| Business validation (rules, quality) | Dagster assets |
| Ingestion status | Dagster (run state via GraphQL) |
| Data serving | FastAPI + DuckLake |
| Operational logs | JSONL files |
| Metrics | `/metrics` → Prometheus |
| Application logs | Python logging → stderr |

## Consequences

- Every asset goes through DuckLake — no alternative storage paths.
- Current scope: tabular data, JSON, XML. Binary and ML artifacts are deferred.
- New formats require extending the IO manager, not bypassing it.
- Ingestion tracking ID = Dagster run ID. No extra status infrastructure.
- Logs are JSONL files, not in DuckLake. Queryable via DuckDB when needed.
- Stations stay lightweight: no message broker, no Prometheus server, no extra databases.
- Postgres init script creates `ducklake` database alongside `dagster`.
