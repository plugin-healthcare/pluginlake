# ADR-004: Data organization and naming conventions

- **Status:** Proposed
- **Date:** 2026-02-24
- **Authors:** Yannick Vinkesteijn

## Context

pluginlake needs a consistent data organization model that connects three layers:

1. **Filesystem/object storage**: Storage layer containing data as open format files (e.g., Parquet).
2. **DuckLake catalog**: Metadata layer containing schemas and tables that reference those files.
3. **Dagster assets**: Orchestration/compute layer containing the pipeline objects that produce and consume data.

These three must stay aligned. If they diverge, data exists on disk but not in the catalog, or assets produce outputs that can't be found. This ADR decides how they relate and what conventions keep them connected.

### Constraint: DuckDB's three-level naming

DuckDB supports exactly three levels: `catalog.schema.table` ([docs: name qualification](https://duckdb.org/docs/stable/sql/statements/attach.html#name-qualification)). There is no nested schema support, so structures like `ducklake.raw.omop.condition_era` (4 levels) are not possible.

### What DuckLake controls

DuckLake fully manages its own file layout within `DATA_PATH` ([docs: paths](https://ducklake.select/docs/stable/duckdb/usage/paths)). When you create a table in a schema, DuckLake automatically creates:

```
DATA_PATH/
└── {schema}/
    └── {table}/
        └── ducklake-{uuid}.parquet
```

We cannot (and should not) override this. DuckLake uses UUIDs for immutability and concurrency safety. The catalog metadata in PostgreSQL tracks which files belong to which table and version.

Key behaviors:

- **Inserts create new files.** DuckLake never appends to or modifies existing Parquet files. Each INSERT produces a new file.
- **Tables naturally become multi-file.** Large inserts are split based on `target_file_size` (default 512 MB). Repeated inserts accumulate files over time.
- **Updates and deletes are copy-on-write.** An UPDATE creates a new data file plus a small delete file referencing rows to skip in the original. DELETE creates only a delete file.
- **Compaction merges small files.** Maintenance functions (`ducklake_merge_adjacent_files`, `ducklake_rewrite_data_files`) consolidate files when needed.
- **Existing files can be registered.** `ducklake_add_data_files()` registers Parquet files already on disk into the catalog without rewriting them.

DuckLake settings like `target_file_size`, `parquet_compression`, and `per_thread_output` can be tuned per table, per schema, or globally via `set_option()` ([docs: configuration](https://ducklake.select/docs/stable/duckdb/usage/configuration)).

**The IO manager only executes SQL.** All file creation, splitting, naming, and lifecycle is handled by DuckLake. There is no file management code in pluginlake.

---

## Decision 1: Processing layers as schemas

**The first segment of a Dagster asset key becomes the DuckLake schema. This represents the processing layer.**

Based on the existing code and lake house conventions, two common patterns are identified:

- Medallion architecture: bronze (raw) → Silver (curated) → gold (aggregated, business-level)
- Domain-based architecture: [omop, fhir, etc.]

A station that uses medallion architecture defines its layers as key prefixes:

```python
@asset(key_prefix="raw")
def omop_condition_era(...) -> pl.DataFrame: ...
# → ducklake.raw.omop_condition_era

@asset(key_prefix="curated")
def omop_condition_era(raw_omop_condition_era: pl.LazyFrame) -> pl.DataFrame: ...
# → ducklake.curated.omop_condition_era
```

A station that doesn't use layers uses domain prefixes directly:

```python
@asset(key_prefix="omop")
def condition_era(...) -> pl.DataFrame: ...
# → ducklake.omop.condition_era
```

Both are valid and the IO manager is able to handle both patterns consistently.

### Full mapping rules

| Dagster asset key | DuckLake schema | DuckLake table | Filesystem path |
|---|---|---|---|
| `["condition_era"]` | `main` | `condition_era` | `DATA_PATH/main/condition_era/` |
| `["omop", "condition_era"]` | `omop` | `condition_era` | `DATA_PATH/omop/condition_era/` |
| `["raw", "omop", "condition_era"]` | `raw` | `omop_condition_era` | `DATA_PATH/raw/omop_condition_era/` |
| `["curated", "omop", "condition_era"]` | `curated` | `omop_condition_era` | `DATA_PATH/curated/omop_condition_era/` |

- **Single-segment key** → schema `main` (DuckDB default), table = key.
- **Multi-segment key** → first segment = schema, remaining segments joined with `_` = table.
- **Filesystem** → managed by DuckLake. Mirrors schema/table structure automatically.

### Schema mapping (optional override)

The IO manager accepts an optional `schema_mapping` dict that overrides the default behavior:

```python
# Remap "raw" prefix to "bronze" schema
DuckLakeIOManager(conn, schema_mapping={"raw": "bronze"})

# ["raw", "omop", "condition_era"] → ducklake.bronze.omop_condition_era
```

This is useful for station-specific naming conventions without changing asset keys.

### Alternatives considered

| Approach | Result for `["raw", "omop", "condition_era"]` | Rejected because |
|---|---|---|
| Layer + domain as combined schema | `ducklake.raw_omop.condition_era` | Schema proliferation: `raw_omop`, `raw_fhir`, `curated_omop`, `curated_fhir`... |
| Domain as schema, layer in table name | `ducklake.omop.raw_condition_era` | Mixes concerns: the domain schema contains all processing stages |
| Nested schemas | `ducklake.raw.omop.condition_era` | Not possible in DuckDB (3-level limit) |

---

## Decision 2: Filesystem layout

The full `.data/` directory layout:

```
.data/
├── lakehouse/          ← DuckLake DATA_PATH (fully managed by DuckLake)
│   ├── raw/
│   │   └── omop_condition_era/
│   │       ├── ducklake-{uuid}.parquet
│   │       └── ducklake-{uuid}.parquet   ← multiple files per table
│   └── curated/
│       └── omop_condition_era/
│           └── ducklake-{uuid}.parquet
├── staging/            ← ingestion payloads awaiting Dagster (see ADR-002)
│   └── {run_id}/
│       └── payload.json
└── logs/               ← JSONL operational logs (see ADR-002)
    ├── query_log/
    └── ingestion_log/
```

- **`lakehouse/`**: Entirely managed by DuckLake. Do not create, move, or delete files here manually.
- **`staging/`**: Temporary holding area for unvalidated ingestion payloads. Organized by Dagster run ID. Lifecycle is described in ADR-002 (ingestion flow).
- **`logs/`**: Operational JSONL logs. Described in ADR-002 (observability).

---

## Decision 3: How the three layers stay connected

The IO manager is the single integration point. It enforces that the Dagster asset key, the DuckLake catalog entry, and the filesystem path are always derived from the same source:

```
Asset key: ["raw", "omop", "condition_era"]
    │
    ├─ IO manager resolves:
    │   schema = "raw"  (first segment, optionally mapped)
    │   table  = "omop_condition_era"  (remaining segments joined with _)
    │
    ├─ DuckLake catalog entry:
    │   ducklake.raw.omop_condition_era
    │
    └─ Filesystem (managed by DuckLake):
        DATA_PATH/raw/omop_condition_era/ducklake-{uuid}.parquet
```

**No manual file management.** The IO manager calls `CREATE OR REPLACE TABLE` and DuckLake handles the rest. There is no code path where files are written to `DATA_PATH` without going through the catalog.

**No name divergence.** The asset key is the single source of truth for the name. The schema, table, and file path are all derived from it. If an asset is renamed, the IO manager writes to the new location on the next materialization.

### What if an asset is renamed?

DuckLake doesn't know about Dagster asset keys — it only knows schemas and tables. Renaming an asset key creates a new table in DuckLake. The old table remains until explicitly dropped. This is acceptable: DuckLake supports time-travel and versioning, so old data isn't lost. A cleanup utility can drop orphaned tables.

## Consequences

- Processing layers (raw, curated, etc.) are DuckLake schemas. The key prefix defines the schema.
- Domain names appear in the table name when layers are used (`raw.omop_condition_era`).
- Stations without layers use domain as schema directly (`omop.condition_era`).
- DuckLake fully manages the filesystem layout. pluginlake contains no file management code.
- Tables are naturally multi-file. Splitting, compaction, and versioning are handled by DuckLake.
- DuckLake settings (`target_file_size`, `parquet_compression`, etc.) can be tuned per table/schema/global.
- Staging and logs live outside DuckLake under `.data/`. Their details are in ADR-002.
- The IO manager is the only integration point between Dagster, DuckLake, and the filesystem.
- Asset renames create new tables; old ones need explicit cleanup.
- Schema mapping allows per-station naming overrides without changing asset code.

---

## Decision 4: Asset data flow and lazy evaluation

### Pipeline data flow

Data flows through the pipeline in two phases per asset boundary:

1. **Read (lazy):** `load_input` returns a `pl.LazyFrame` via `conn.sql(...).pl(lazy=True)`.
2. **Transform:** The asset chains Polars lazy operations (`.filter()`, `.select()`, `.join()`, etc.).
3. **Write (eager):** The asset returns a `pl.DataFrame` (calling `.collect()` if working lazily). `handle_output` registers it in DuckDB and writes to DuckLake via `CREATE OR REPLACE TABLE`.

```
load_input  →  pl.LazyFrame  →  asset transforms (lazy)  →  .collect()  →  pl.DataFrame  →  handle_output
```

### Why lazy reads matter

DuckDB v1.4.0 added native Polars LazyFrame support ([duckdb#17947](https://github.com/duckdb/duckdb/pull/17947)) with:

- **Projection pushdown:** Only columns used by the Polars plan are fetched from DuckDB.
- **Filter pushdown:** Polars `.filter()` expressions are translated to SQL WHERE clauses and pushed down to DuckDB, enabling DuckLake file pruning via `ducklake_file_column_stats`.
- **Batched streaming:** Data flows as Arrow record batches, not as a single materialization.

This means a downstream asset that only uses a few columns and filters on a condition will only read the relevant data from DuckLake, not the full table.

### Why writes are eager

Dagster's IO manager contract requires `handle_output` to receive a Python object. The asset must return a materialized `pl.DataFrame`. This is a Dagster framework constraint, not a DuckLake limitation. DuckLake itself can write from SQL queries without Python materialization (see future features: `DuckDBPyRelation` dispatch).

### Bounded ingestion

Data enters the pipeline in bounded chunks, either through:

- **Dagster partitions:** Each partition is a separate materialization processing a manageable slice.
- **API-level chunking:** The FastAPI ingestion endpoint accepts bounded payloads (e.g., FHIR bundles of N resources). Each payload triggers a Dagster run for that chunk.

This ensures the pipeline never processes unbounded data in a single materialization. The DuckLake table accumulates across runs since each INSERT creates new Parquet files without modifying existing ones.

### Serving layer

The FastAPI serving layer queries DuckLake directly via SQL with proper WHERE clauses. It does not use the IO manager. This means:

- Selective reads benefit from DuckLake file pruning naturally.
- No data enters Python beyond what the query returns.
- The serving layer is decoupled from pipeline execution.
