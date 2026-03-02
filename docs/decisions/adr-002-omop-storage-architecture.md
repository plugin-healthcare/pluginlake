# ADR-002: OMOP data storage architecture

- **Status:** Proposed
- **Date:** 2026-02-17 (revised 2026-03-01)
- **Authors:** Tim Hendriks

## Context

pluginlake needs to store and query hospital data in different formats and coming from multiple sources. We need a storage solution that:

- Can ingest OMOP, FHIR, tabular data and more
- Supports analytical queries on large healthcare datasets
- Preserves the native OMOP table structure for compatibility with existing OMOP tooling
- Enables efficient compression and columnar access patterns
- Provides data versioning and lineage tracking
- Maintains type safety and schema validation

## Decision

**All data assets are written through the Dagster IO manager, which issues `CREATE OR REPLACE TABLE` SQL against the DuckLake catalog. DuckLake manages all Parquet files autonomously. No manual Parquet file management exists in pluginlake.**

### Write path: Dagster IO manager → DuckLake

Every data asset is written through `DuckLakeIOManager.handle_output()`, which executes:

```sql
CREATE OR REPLACE TABLE ducklake.<schema>.<table> AS SELECT * FROM _data
```

DuckLake translates this into immutable, UUID-named Parquet files on disk. Updates and deletes use copy-on-write markers — pluginlake never rewrites files directly.

### Storage layout (managed by DuckLake)

```
data/lakehouse/
└── <schema>/
    └── <table>/
        └── ducklake-<uuid>.parquet
```

The `data/lakehouse/` root is set via `DUCKLAKE_DATA_PATH`. There is no `data/storage/` directory; DuckLake is the single storage root.

### Data flow

```
CSV files (OMOP CDM format)
    ↓
Polars loader (pluginlake.omop.loader)
    ↓
Dagster asset (pluginlake.assets.omop)
    ↓
DuckLakeIOManager.handle_output()
    ↓
CREATE OR REPLACE TABLE ducklake.omop.<table>
    ↓
DuckLake → ducklake-<uuid>.parquet
```

**Key points:**

- OMOP CSVs from Synthea are a **direct input format**, not only a transformation target
- The Dagster IO manager is the single write path — no asset may bypass it (ADR-003)
- DuckLake handles file naming, compaction, and copy-on-write internally

### Query/serve path

FastAPI reads directly from the DuckLake catalog via SQL:

```sql
SELECT * FROM ducklake.omop.person WHERE ...
```

No intermediate view registration step (`register_omop_tables`) is needed in the serving layer.

### Asset key routing

`["omop", "person"]` → `ducklake.omop.person` (handled by `DuckLakeIOManager`)

## Alternatives considered

### Manual Parquet files + DuckDB view registration

Write Parquet files directly from Polars, then register them as DuckDB views with `register_omop_tables()`.

**Rejected because:**

- Bypasses the DuckLake catalog, losing versioning and lineage
- Requires pluginlake to manage file paths and overwrites explicitly
- No copy-on-write support; full file rewrites needed for any update
- Violates ADR-003 ("every data asset goes through DuckLake")

### PostgreSQL for all data storage

Store FHIR, tabular, and OMOP data directly in PostgreSQL.

**Rejected because:**

- OLTP-optimized, not OLAP (slower analytical queries)
- No built-in compression
- Harder to version entire datasets atomically

## Consequences

### Positive

- **Single write path**: all assets go through the IO manager — no ad-hoc Parquet writes
- **DuckLake manages files**: UUID-named files, copy-on-write updates, no manual overwrite logic
- **Fast analytical queries**: columnar format + predicate pushdown via Polars `LazyFrame`
- **Versioning and lineage**: DuckLake PostgreSQL catalog tracks all table versions
- **Portable storage**: Parquet files are readable without DuckLake if needed

### Negative

- **DuckLake maturity**: newer project, less battle-tested than PostgreSQL
- **Memory constraints**: DuckDB requires sufficient RAM for large queries (mitigated by spillover to disk)

## Migration note

`omop/storage.py` (`save_omop_table`, `register_omop_tables`, `get_duckdb_connection`) implements the pre-DuckLake manual path and is deprecated. It will be removed once `queries.py` and `vocabulary_queries.py` are migrated to read directly from `ducklake.omop.*`.
