# ADR-002: OMOP data storage architecture

- **Status:** Proposed
- **Date:** 2026-02-17
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

**Store all healthcare data (FHIR, tabular, OMOP) as Parquet files. Transform all data to OMOP for use with DuckDB for analytical queries, using DuckLake for catalog management.**

### Storage layer: Parquet files

All healthcare data is stored as Parquet files, organized by source format:

```
data/storage/
├── fhir/                    # Native FHIR resources from EPD systems
│   ├── patient.parquet      # Nested: id, name[{family, given[]}], identifier[{}]
│   ├── observation.parquet  # Nested: id, subject{}, code{}, value[x]
│   └── encounter.parquet
├── tabular/                 # Flat tables from legacy systems
│   ├── lab_results.parquet
│   └── appointments.parquet
└── omop/                    # Transformed to OMOP CDM v5.4
    ├── person.parquet
    ├── observation_period.parquet
    ├── visit_occurrence.parquet
    └── condition_occurrence.parquet
```

**Rationale:**

- **Columnar format**: Optimized for analytical queries (80-90% compression ratio)
- **Self-describing schema**: Embedded metadata - no external schema files needed, data is portable
- **Nested types support**: FHIR resources contain nested arrays and objects (e.g., `Patient.name[{family, given[]}]`), Parquet preserves this structure without flattening
- **Format flexibility**: Same storage layer works for flat OMOP tables and hierarchical FHIR resources

### Query layer: DuckDB

DuckDB provides zero-copy analytical queries over Parquet files through registered views.

**Rationale:**

- Embedded analytical database (no server required)
- Native Parquet integration with predicate pushdown
- Excellent performance on OLAP workloads
- Easy conversion to/from Polars DataFrames

### Catalog layer: DuckLake

DuckLake (extension for DuckDB) manages metadata, versioning, and lineage:

- **Metadata catalog**: PostgreSQL backend tracks table versions, schemas, and data locations
- **Version control**: Snapshot-based versioning for reproducible queries
- **Lineage tracking**: Records data transformations and asset dependencies
- **Multi-table transactions**: Ensures consistency across related OMOP tables

### Data flow architecture

```
EPD systems
    ↓
FHIR API / Tabular exports
    ↓
Polars loader (format-specific parsers)
    ↓
Parquet files (native format: fhir/, tabular/)
    ↓
Transformation pipeline
    ↓
Parquet files (OMOP format: omop/)
    ↓
DuckDB views (zero-copy queries on all formats)
    ↓
DuckLake catalog (metadata + versioning + lineage)
```

**Key points:**

- FHIR resources stored with nested structure intact
- Tabular data stored as flat tables
- OMOP is a transformation target, not input format
- OMOP is the **primary analytical interface** for cross-station federated queries
- Lineage tracks FHIR → OMOP transformations

## Alternatives considered

### Only store data as OMOP

Transform incoming data first, and use only OMOP as the standard for data storage. In this case the lineage information on the data transformation would be lost.

**Rejected because:**

- Loses original FHIR structure needed for EPD system reconciliation
- Cannot regenerate source data if transformation logic changes
- OMOP may not capture all FHIR-specific elements (extensions, custom fields)
- Makes debugging transformation issues harder
- Irreversible data loss for non-OMOP use cases

### Store data in another dataformat and generate OMOP on the fly

Store data in a different format (e.g., FHIR in JSON files), and generate OMOP dynamically when needed.

**Rejected because:**

- Repeated transformation overhead on every query
- No materialized OMOP views for fast analytical queries
- Complex transformation logic must run at query time
- Cannot validate OMOP compliance until query execution
- Poor performance for federated queries across stations

### PostgreSQL for all data storage

Store FHIR, tabular, and OMOP data directly in PostgreSQL database.

**Rejected because:**

- OLTP-optimized, not OLAP (slower analytical queries)
- No built-in compression (requires extensions)
- Harder to version entire datasets atomically

## Consequences

### Positive

- **Fast analytical queries**: Columnar format + predicate pushdown enable efficient filtering
- **Portable storage**: Parquet files work across languages and platforms
- **Type-safe ingestion**: Pydantic validation catches errors early
- **Easy development**: No database server required for local work
- **Efficient storage**: 80-90% compression reduces storage costs
- **Versioning ready**: DuckLake enables reproducible queries

### Negative

- **No row-level updates**: Must rewrite entire Parquet files to modify data (acceptable because we will append-only)
- **DuckLake maturity**: Newer project, less battle-tested than PostgreSQL
- **Memory constraints**: DuckDB requires sufficient RAM for large queries (mitigated by spillover to disk)
