# ADR-007: Column-level lineage strategy

- **Status:** Proposed
- **Date:** 2026-04-12
- **Authors:** Yannick Vinkesteijn, Daniel Kapitan

## Context

pluginlake tracks asset-level lineage through Dagster's dependency graph: we know that `omop.condition_era` depends on `omop_raw.condition_era`. We do not know which *columns* in the output came from which columns in the input, or how they were derived. This matters for:

- **Impact analysis:** changing a source column → which downstream columns break?
- **Compliance:** healthcare data requires knowing where patient identifiers flow.
- **Documentation:** data stations add custom assets; consumers need to understand column provenance without reading Python code.

This ADR evaluates the available tooling and approaches for adding column-level lineage to pluginlake's existing Dagster + Polars + DuckLake setup.

## Constraints

pluginlake's architecture imposes specific constraints on any lineage solution:

1. **No dbt.** Transformations are Dagster assets with Polars/DuckDB, not dbt SQL models (ADR-001).
2. **Runtime, not build-time.** `can_subset=True`, `diagonal_relaxed`, `SELECT *`, polymorphic FHIR data, and custom data station assets mean column mappings can only be fully determined at materialization time (ADR-001, ADR-003).
3. **DuckLake is the catalog.** All data and metadata flows through DuckLake (ADR-003). A lineage solution that stores results outside the catalog fragments the metadata layer.
4. **Extensibility.** Data stations add custom assets (ADR-001). Lineage must work for assets pluginlake has never seen, not only for a pre-defined set.
5. **Network isolation.** Data stations run inside hospital or research networks with strict egress controls. External services are not reachable from these environments. Lineage is captured on every materialization run, so any dependency on outbound connectivity would affect every pipeline execution.
6. **LLM resource requirements (open question).** If a solution relies on LLM inference for lineage capture or enrichment, this raises questions worth examining: (a) cloud-hosted LLMs are not reachable from isolated hospital networks, so a local model would be required; (b) local LLMs carry significant compute and memory requirements. Whether the value of AI-assisted lineage justifies making a capable inference server a deployment prerequisite for every data station needs to be weighed.

## Options considered

### Option A: Altimate AI (dbt Power User)

[Altimate AI](https://github.com/AltimateAI/vscode-dbt-power-user) is a VS Code extension that provides column-level lineage for **dbt projects**. It parses Jinja+SQL models, follows `{{ ref() }}` and `{{ source() }}` references, and renders lineage in the editor.

| Criterion | Assessment |
|-----------|------------|
| dbt requirement | **Blocking.** Requires `dbt_project.yml`, `models/`, dbt manifest/catalog. pluginlake has none of these (we use Dagster assets). |
| SQL-only | Column lineage works on SQL models. pluginlake's Polars DataFrame transformations (`filter`, `join`, `with_columns`, `group_by`) are invisible to it. |
| Static analysis | Parses source code at development time. Cannot handle `can_subset=True` (columns selected at runtime), `SELECT *` (schema not known until execution), or custom data station assets (code not available to the analyzer). |
| Integration | Column lineage is rendered locally from dbt manifest/catalog artifacts (no cloud required for that feature). AI-assisted features (doc generation, query explanation) require an Altimate API key that calls an external LLM endpoint. |
| LLM dependency (cloud) | Column lineage requires an API key (verified in the official docs: model lineage works without a key, column lineage does not). This means even column lineage makes outbound cloud calls, not only the AI-enrichment features. Hospital and research networks block outbound API calls to third-party services (constraint 5). |
| LLM dependency (local) | If a local LLM were substituted, it would need to run on every data station server. This raises the question of whether AI-assisted lineage is valuable enough to justify the compute and memory overhead of running a local model as part of the pipeline infrastructure (constraint 6). |
| Custom assets | Data stations would need to maintain a parallel dbt project to get lineage, which defeats the purpose of the Dagster-based extensibility model. |
| Cost | Model lineage (no column detail) is free without a key. Column lineage requires a free API key, but obtaining one creates an account dependency and outbound calls at runtime. AI/LLM-powered features (doc generation, query explanation) require a paid subscription. |
| Altimate Datamates | Altimate also offers a separate "Datamates" product supporting Snowflake, Databricks, and BigQuery as a broader AI data engineering assistant. This does not add Dagster or Polars lineage support. |

**Verdict: does not fit the current stack as a primary lineage solution.** The dbt requirement is a hard blocker: there is no dbt project to parse, and creating one would duplicate all transformation logic. Polars assets are invisible to SQL-based static analysis regardless. The AI/LLM dependency introduces additional questions around network isolation (constraint 5) and server resource requirements (constraint 6) that should be answered before any AI-assisted tooling is considered for production use in this context.

### Option B: Dagster native `TableColumnLineage`

Since Dagster 1.7, assets can emit [`TableColumnLineage`](https://docs.dagster.io/concepts/metadata-tags/asset-metadata/table-metadata#attaching-column-lineage) metadata on `MaterializeResult`. The Dagster UI renders this as an interactive column-level lineage graph.

| Criterion | Assessment |
|-----------|------------|
| dbt requirement | None. Works with any Dagster asset. |
| Polars support | No built-in inference, but accepts manually constructed `TableColumnDep` objects. |
| Runtime | Metadata is emitted at materialization time, which naturally fits our runtime model. |
| Integration | Native Dagster. Lineage visible in the same UI operators already use. |
| Custom assets | Data stations can emit `TableColumnLineage` from their assets. |
| Storage | Stored in Dagster's event log (PostgreSQL). Not in DuckLake, but queryable via GraphQL. |

**Verdict: right API, no automatic inference.** `TableColumnLineage` is the correct output format, but every asset would need to manually declare its column mappings. For dynamic assets (`can_subset=True`, FHIR polymorphism), manual declarations are error-prone and hard to maintain.

### Option C: plugin-lineage (custom inference library)

A fully custom library that infers column-to-column lineage by inspecting execution plans at runtime:

- **SQL path:** a custom SQL parser (e.g. sqlglot) parses DuckDB SQL and traces column provenance through joins, filters, and projections.
- **Polars path:** `LazyFrame.serialize(format="json")` exposes the query plan as JSON. A walker resolves column mappings from plan nodes (`Select`, `HStack`, `Join`, `Filter`, `GroupBy`).

| Criterion | Assessment |
|-----------|------------|
| dbt requirement | None. Works with SQL strings and Polars LazyFrames. |
| Polars support | First-class. Walks the serialized plan JSON. |
| Runtime | Inspects the actual plan/query at materialization time. Handles `can_subset`, `SELECT *`, and dynamic schemas. |
| Integration | Library dependency of pluginlake. Output: `TableColumnLineage` metadata on Dagster + DuckLake `lineage.*` tables. |
| Custom assets | Works on any asset that produces SQL or a LazyFrame, including data station custom assets. |
| Storage | Persists to DuckLake (consistent with ADR-003) and emits Dagster metadata (visible in UI). |
| Cost | Open source. No SaaS dependency. |
| Maturity | Not yet implemented. Requires significant development effort for both the SQL and Polars walkers, plan node coverage, and ongoing maintenance against Polars internal changes. |
| Standardization | Proprietary format. Not interoperable with external lineage consumers without building a separate export layer. |

**Verdict: addresses the core constraints but reinvents the wheel.** Building a custom lineage engine from scratch means owning the full problem: SQL parsing, plan walking, the event format, storage, and any future interoperability. OpenLineage already provides a mature, vendor-neutral standard for the event model and the SQL extraction layer. The Polars gap is real but narrower than building an entire lineage system.

### Option D: OpenLineage

[OpenLineage](https://openlineage.io) is an open standard for lineage events. It defines a JSON event model where producers emit `RunEvent` messages describing inputs, outputs, and facets (structured metadata). Column-level lineage is represented via the `ColumnLineageDatasetFacet`, which maps each output column to its input columns with transformation type (`DIRECT`/`INDIRECT`) and subtype (`IDENTITY`, `JOIN`, `AGGREGATION`, etc.).

| Criterion | Assessment |
|-----------|------------|
| Column lineage | The spec has first-class support via `ColumnLineageDatasetFacet`. It distinguishes per-column dependencies (`fields`) from dataset-level influences (`dataset`, e.g. join predicates, filters). |
| DuckDB integration | The [`duck_lineage`](https://duckdb.org/community_extensions/extensions/duck_lineage) community extension automatically captures column-level lineage from every DuckDB query and emits OpenLineage events. It extracts input/output datasets and column dependencies from DuckDB's logical query plan, supports `CREATE TABLE AS`, `INSERT INTO SELECT`, joins, aggregations, window functions, `PIVOT`, `UNNEST`, star expansion, and file scans. It has explicit **DuckLake support** with automatic namespace resolution from `DATA_PATH`. No SQL parsing library needed: lineage is extracted natively inside DuckDB. |
| Spark support | First-class. The OpenLineage Spark integration captures column-level lineage automatically from Spark jobs. Relevant if pluginlake or data stations adopt Spark for large-scale processing. |
| dbt integration | The dbt integration reads `manifest.json` and compiled SQL to produce column lineage facets. It explicitly supports the `duckdb` adapter. Column-level lineage landed in OpenLineage 1.25. |
| Dagster integration | [`openlineage-dagster`](https://pypi.org/project/openlineage-dagster/) (v1.38.0) provides an OpenLineage sensor that tails Dagster event logs and converts them to OpenLineage events. It captures job and op lifecycle metadata. Configuration is via environment variables (`OPENLINEAGE_URL`, `OPENLINEAGE_API_KEY`, `OPENLINEAGE_NAMESPACE`). Column-level lineage bridging from Dagster's `TableColumnLineage` to OpenLineage facets is not automatic and needs to be built. |
| Polars support | **No Polars integration exists.** OpenLineage has extractors for Spark, BigQuery, Snowflake, and dbt, but not Polars. This is the primary gap for pluginlake and must be addressed with custom work (see implementation section). |
| Transport | OpenLineage is transport-agnostic. Events can be sent to HTTP (Marquez or custom), file (JSONL), console, Kafka, or a custom transport. Marquez is not required. For `duck_lineage`, transport is configured via `SET duck_lineage_url` (HTTP to any OpenLineage backend). For `openlineage-dagster`, transport is configured via `OPENLINEAGE_URL`. |
| Standard | Open, vendor-neutral, Linux Foundation project. Adopted by Spark, Airflow, dbt, Flink, and others. Aligning with this standard means pluginlake's lineage is immediately interoperable with the broader data ecosystem. |

**Verdict: the right standard, with a solvable gap.** OpenLineage provides a mature event model, SQL extraction, and broad ecosystem support. The Polars gap is real but bounded: pluginlake needs to build a decorator-based lineage wrapper for Python/Polars pipelines and contribute column dependency extraction using Polars' own `Expr.meta` API. This is less work than building an entire custom lineage system (Option C), and the result is interoperable rather than proprietary.

## Decision

**Column-level lineage will be implemented using OpenLineage (Option D) as the lineage standard, with Dagster `TableColumnLineage` (Option B) as the in-process metadata format for the Dagster UI.**

OpenLineage provides the event model, the SQL extraction layer, and ecosystem interoperability. Dagster's `TableColumnLineage` provides native UI rendering. Both are populated from the same inferred column dependencies.

The Polars/Python gap in OpenLineage is real: no extractor exists for Polars pipelines. pluginlake will address this with a **decorator-based lineage wrapper** (`@track_lineage`) and selective use of Polars `Expr.meta` for automatic column dependency extraction where expressions are available. For fully opaque transforms (e.g. FHIR-to-OMOP translation via Python dicts), lineage is declared explicitly on the decorator.

A fully custom lineage engine (Option C, plugin-lineage) is not adopted. OpenLineage already solves the SQL and event model layers; building those from scratch would duplicate work without adding interoperability.

Altimate AI (Option A) is not adopted: pluginlake is not a dbt project and Polars assets are invisible to SQL-based static analysis.

### Integration design

pluginlake has three distinct lineage extraction paths, reflecting the actual transformation patterns in the codebase:

```text
Asset materializes
  │
  ├─ SQL path (automatic, zero-config)
  │   duck_lineage DuckDB extension intercepts all queries
  │   └─ logical plan → column lineage → OpenLineage events (HTTP)
  │
  ├─ Dagster lifecycle (automatic)
  │   openlineage-dagster sensor tails event logs
  │   └─ job/op START/COMPLETE/FAIL → OpenLineage events
  │
  ├─ Polars expression path (semi-automatic)
  │   select(), with_columns(), filter(), group_by() etc.
  │   └─ Expr.meta.root_names() + output_name() → column lineage
  │
  ├─ Opaque Python path (declarative)
  │   translator.translate_record(), map_elements, UDFs
  │   └─ @track_lineage decorator with explicit column mapping
  │
  └─ Column lineage records
      ├─ → TableColumnLineage metadata on MaterializeResult (Dagster UI)
      ├─ → OpenLineage RunEvent with ColumnLineageDatasetFacet
      └─ → DuckLake lineage.column_mappings table (queryable, persistent)
```

### Current pipeline patterns and their lineage paths

Grounding the design in the actual codebase:

| Asset | Pattern | Lineage path |
|-------|---------|--------------|
| `omop_raw_clinical_tables` | `load_omop_dataset()` → yield DataFrame | **Identity.** All columns pass through unchanged. Automatic. |
| `omop_clinical_tables` | `conn.sql("SELECT * FROM {ref}")` → `pl.concat()` → `filter()` | **SQL + Polars.** SQL extracts column lineage from `SELECT *`. Filter is an INDIRECT dependency. |
| `fhir_raw_tables` | `load_fhir_dataset()` → yield DataFrame | **Identity.** Single `json_data` column passes through. Automatic. |
| `fhir_to_omop_tables` | `translator.translate_record(dict)` → `pl.DataFrame(rows)` | **Opaque.** Python dict manipulation. Requires `@track_lineage` with explicit mapping. |
| `omop_vocabulary_tables` | `load_vocabulary_dataset()` → yield DataFrame | **Identity.** Automatic. |

### Transport

Each emission path has its own transport:

- **`duck_lineage`** and **`openlineage-dagster`** both emit via HTTP to an OpenLineage-compatible endpoint. In network-isolated environments, this means running a local receiver (e.g. Marquez or a lightweight HTTP-to-file bridge on the same host).
- **`openlineage-python`** (used by the `@track_lineage` decorator for Polars) supports HTTP, file (JSONL), console, and Kafka transports.

For unified lineage collection, all environments should run a local OpenLineage HTTP endpoint so all three emission paths converge at the same backend. The receiver is Marquez, see [Addendum: Marquez as OpenLineage receiver](#addendum-marquez-as-openlineage-receiver).

### SQL path: `duck_lineage` extension

The SQL path requires no custom code. The [`duck_lineage`](https://github.com/ilum-cloud/duck_lineage) DuckDB community extension intercepts every query and emits OpenLineage events with column-level lineage extracted from DuckDB's logical query plan. It has explicit **DuckLake support** with automatic namespace resolution from `DATA_PATH`.

This covers all SQL in pluginlake: IO manager writes, asset queries, vocabulary validation, and data station custom assets. It supports joins, aggregations, window functions, `CTAS`, `INSERT INTO SELECT`, star expansion, file scans, `PIVOT`, `UNNEST`, and more.

The extension only supports HTTP transport. Network-isolated environments need a local OpenLineage-compatible endpoint.

If data stations adopt dbt, column lineage from dbt models comes for free via `openlineage-dbt` (which supports the `duckdb` adapter).

### Polars/Python lineage: the gap and the direction

OpenLineage has no Polars integration. The Polars team has [indicated](https://github.com/pola-rs/polars/issues/11031) that built-in column-level lineage tracking may be reserved for Polars Cloud rather than core. This is the primary gap pluginlake needs to fill.

**Key finding: `Expr.meta` works on expressions, not DataFrames.** Polars provides `Expr.meta` methods (`root_names()`, `output_name()`, `is_literal()`, etc.) that resolve column dependencies from an expression. However, these only work on `Expr` objects *before* they are applied to a DataFrame. Once a transform executes, expression metadata is gone. Lineage extraction must intercept expressions at the call site, before execution.

**Direction: a `@track_lineage` decorator** that wraps asset or transform functions with three modes:

1. **Automatic:** intercept expressions passed to `select()`, `with_columns()`, `filter()`, `group_by()` etc. and call `Expr.meta.root_names()` / `output_name()` to infer column dependencies.
2. **Explicit:** accept a declarative column mapping for opaque transforms (FHIR translators, `map_elements`, UDFs) where `Expr.meta` cannot help.
3. **Identity:** for raw ingestion assets that pass all columns through unchanged.

The decorator would emit both Dagster `TableColumnLineage` metadata and OpenLineage `ColumnLineageDatasetFacet` events. Dataset-level influences (join keys, filter predicates, group-by columns) would be recorded as INDIRECT dependencies.

This is the only substantial custom work in the architecture. If Polars adds native lineage or an `openlineage-polars` community extractor emerges, the decorator can be replaced without changing asset code. If our implementation matures, it could be contributed upstream as a reusable package.

**Open questions to validate before building:**

- Can expression interception be done cleanly via wrapping, or does it require monkey-patching Polars methods?
- How do wildcard selectors (`pl.all()`, `pl.exclude()`) interact with `Expr.meta`?
- What is the performance overhead of `Expr.meta` calls on every Polars operation?
- Is a decorator the right abstraction, or should lineage capture live at the IO manager level?

### Where lineage extraction runs

Lineage is captured at three levels:

1. **DuckDB engine level (SQL path).** The `duck_lineage` extension intercepts every query executed against DuckDB and emits OpenLineage events with column-level lineage automatically. This requires no code changes in assets or the IO manager beyond loading the extension at connection initialization.

2. **Dagster instance level (lifecycle events).** The `openlineage-dagster` sensor tails Dagster event logs and emits OpenLineage events for job/op lifecycle (START, COMPLETE, FAIL). This provides run-level lineage and links DuckDB query lineage to Dagster asset runs via the `OPENLINEAGE_PARENT_*` environment variables that `duck_lineage` supports.

3. **Asset/transform function level (Polars/Python path).** The `@track_lineage` decorator wraps individual asset functions or transform helpers. It captures `Expr.meta` from Polars operations and accepts explicit mappings for opaque transforms. The decorator emits both Dagster `TableColumnLineage` metadata and OpenLineage events for the Python-side column dependencies that `duck_lineage` cannot see.

### What changes in pluginlake

The work falls into three tiers:

**Tier 1: configuration only (SQL + Dagster lifecycle lineage)**

- Load `duck_lineage` extension at DuckDB connection initialization
- Add `openlineage-dagster` dependency and configure sensor
- Set `OPENLINEAGE_PARENT_*` env vars so `duck_lineage` events link to Dagster runs
- Stand up a local OpenLineage HTTP endpoint (Marquez, see the addendum below)

**Tier 2: migration (Dagster best practice, independent of lineage)**

- Migrate `Output()` to `MaterializeResult` across asset files (prerequisite for attaching metadata)

**Tier 3: custom build (Polars/Python lineage)**

- Build `@track_lineage` decorator with `Expr.meta`-based extraction
- Annotate FHIR translators with explicit column mappings
- Create `lineage` schema in DuckLake for persistent queryable storage

#### Schema contracts via LinkML (refinement, not prerequisite)

The OMOP CDM has an official `linkml-omop` schema that formally types every table and column. If pluginlake adopts it, the output column set of OMOP assets becomes statically known, which simplifies identity lineage declarations and could replace ad-hoc column definitions elsewhere. This is worth exploring once the core lineage approach is validated.

## Consequences

### Positive

- Column-level impact analysis for all assets, including custom data station assets.
- OpenLineage standard, not a custom format. Interoperable with Spark, Airflow, dbt, Marquez.
- SQL path requires zero custom code (`duck_lineage` handles it automatically).
- Dagster lifecycle lineage is a config change (`openlineage-dagster` sensor).
- Lineage visible in Dagster UI via `TableColumnLineage`.
- No vendor lock-in. `duck_lineage` (MIT) and `openlineage-dagster` (Apache 2.0) are open source.
- `@track_lineage` decorator is non-invasive and replaceable if Polars or OpenLineage adds native support.
- dbt lineage comes for free if data stations adopt it.

### Negative

- Building the `@track_lineage` decorator is the only substantial custom work.
- `Expr.meta` only works on expressions before execution, requiring interception at the call site.
- Opaque transforms (FHIR, `map_elements`) need manually maintained column mappings.
- `Output()` to `MaterializeResult` migration touches all asset files.
- `duck_lineage` only supports HTTP transport: isolated environments need a local endpoint.
- `openlineage-dagster` notes "New integration maintainers are needed!" on PyPI.

### Risks

- **`Expr.meta` is expression-only.** Cannot track lineage through materialized DataFrames. Mitigation: explicit mapping mode.
- **Polars Cloud vs core** ([pola-rs/polars#11031](https://github.com/pola-rs/polars/issues/11031)). Native lineage may become a paid feature. Mitigation: depend only on existing public `Expr.meta` API.
- **Interception complexity.** Wrapping `with_columns()`, `select()`, `join()`, `filter()` etc. is non-trivial. Edge cases (`pl.all()`, `pl.exclude()`, nested expressions) need testing.
- **Event volume.** `duck_lineage` emits per query, not per materialization. Needs retention policy.
- **Multi-hop lineage.** `root_names()` traces within one expression, not across upstream assets. Full pipeline lineage needs Dagster's asset dependency graph.

## Addendum: Marquez as OpenLineage receiver

- **Date:** 2026-10-14, updated 2026-10-15
- **Issue:** #219, #220

The open question under [Transport](#transport) is settled: the station runs [Marquez](https://marquezproject.ai) as its local OpenLineage receiver.

### Why Marquez

- It is the reference implementation of the OpenLineage API, so `duck_lineage`, the Dagster bridge and `openlineage-python` can all post to it without adapters.
- It stores events in PostgreSQL and comes with a web UI for browsing jobs, datasets and lineage graphs, which a file-based bridge would not give us.
- It runs fully inside the station network, with no outbound connectivity (constraint 5).

A lighter HTTP-to-file bridge was considered, but it would only store events; viewing them would still need a separate tool. Marquez can be replaced later by any OpenLineage-compatible backend, because emitters only depend on the endpoint URL.

### Marquez vs OpenMetadata

[OpenMetadata](https://open-metadata.org) was also considered. It is a full metadata platform (catalog, search, glossary, classification, data quality, ownership, RBAC) with lineage as one feature, whereas Marquez is a focused OpenLineage store.

| | Marquez | OpenMetadata |
|---|---|---|
| Scope | Lineage only: jobs, runs, datasets, column lineage | Catalog, discovery, glossary, tags, data quality, profiling, ownership, policies and lineage |
| OpenLineage | Reference implementation, native `/api/v1/lineage` endpoint | Own metadata model; OpenLineage is ingested through a connector |
| Components | API, web UI, PostgreSQL (OpenSearch optional) | Server, MySQL or PostgreSQL, Elasticsearch/OpenSearch (required), ingestion runner (Airflow-based by default), UI |
| Footprint | Small: three containers, about 1 GB RAM | Large: about 4+ vCPU and 8+ GB RAM, mostly for OpenSearch |
| Auth | None | SSO, RBAC, bot tokens |
| Ingestion model | Push: producers emit events | Mainly pull: scheduled connectors scan sources |
| Project activity | Slowing; last release 0.51.1 (early 2025) | Very active, backed by Collate |

Fit with the pluginlake constraints:

| Constraint | Marquez | OpenMetadata |
|---|---|---|
| Network-isolated, small station hosts (constraint 5) | Fits: lightweight and fully local | Heavy to operate on every station (OpenSearch and an ingestion runner) |
| DuckLake is the catalog (constraint 3, ADR-003) | Adds lineage only, no overlap with DuckLake | Introduces a second catalog next to DuckLake, fragmenting the metadata layer |
| OpenLineage as the standard (this ADR) | Native for `duck_lineage`, `openlineage-dagster` and `@track_lineage` | Supported, but through an extra translation step |
| Authorization via Nuts and the Dataspace Protocol (ADR-006, ADR-008) | No auth of its own; kept behind host loopback | Brings its own SSO and RBAC, a second access-control system next to Nuts/DSP |
| DCAT dataset metadata (#191) | Not covered | Partly covered by catalog features, no DCAT output out of the box |

Conclusion:

- **Per station: Marquez.** The station needs a local, lightweight OpenLineage receiver, which is exactly what Marquez provides.
- **Central or network level: OpenMetadata is a candidate later**, if cross-station discovery, a glossary, PII classification or data quality dashboards become requirements. It would then run once centrally and be fed from the stations (via DCAT or forwarded OpenLineage events), not on every node.
- **Switching stays cheap.** Emitters only know the OpenLineage endpoint, and the OpenLineage client can send each event to several destinations, so Marquez and another receiver can run side by side during a migration.
- **Risks to watch for Marquez:** the slowing upstream activity (keep the image pinned and review periodically) and the lack of authentication (keep the UI behind loopback, an SSH tunnel or an authenticating reverse proxy).

### Configuration

- Marquez is optional and runs as the `lineage` compose profile in `deploy/compose/docker-compose.dev.yaml`, with three services: `marquez-db`, `marquez` (API) and `marquez-web` (UI).
- It is switched on with `lineage = true` under `[station]` in `pluginlake.toml`; `pluginlake up` then activates the profile. `pluginlake down` always stops all profiles.
- Images are pinned by version: `marquezproject/marquez:0.51.1` and `marquezproject/marquez-web:0.51.1`.
- Marquez uses its own PostgreSQL container (`marquez-db`) and database, separate from the Dagster and DuckLake database. Credentials are set with `MARQUEZ_DB`, `MARQUEZ_DB_USER` and `MARQUEZ_DB_PASSWORD` in `deploy/compose/.env`.
- Data lives in the named volume `marquez-db-data`, so it survives `pluginlake down` and restarts. Only `pluginlake down -v` removes it.
- The API config is `config/marquez/marquez.yml`: credentials come from the environment, OpenSearch-based search is explicitly disabled (it is not part of the stack), and the `PII` and `SENSITIVE` tags are predefined.
- The OpenLineage endpoint inside the compose network is `http://marquez:5000/api/v1/lineage`. The API is not published on the host.
- Marquez has no authentication. The web UI is therefore published on the host loopback interface only (`127.0.0.1:3001`, override with `MARQUEZ_WEB_PORT`), so only administrators with access to the host (for example through an SSH tunnel) can reach it.

### Dagster lifecycle lineage: a core bridge instead of `openlineage-dagster`

`openlineage-dagster` cannot be used: its latest release (1.38.0) pins `dagster<=1.6.9` while pluginlake runs Dagster 1.13, and the package is unmaintained ("New integration maintainers are needed!"). The Dagster tier is therefore implemented as a small core bridge built on `openlineage-python`, following the approach of [srdp](https://github.com/srdp-hub/srdp) (`srdp.lineage.openlineage_bridge`, srdp ADR-0003). It keeps the standard OpenLineage configuration (`OPENLINEAGE_URL`, `OPENLINEAGE_NAMESPACE`):

- `openlineage_sensor` (`pluginlake.definitions.lineage`) is a run-status sensor on `SUCCESS`, evaluated by the Dagster daemon. Core merges it into the `pluginlake.definitions` code location, so projects get lineage without registering anything.
- The bridge (`pluginlake.core.lineage.openlineage_bridge`) turns every asset materialized in the run into one OpenLineage `COMPLETE` `RunEvent`: the asset is the job, its upstream assets from the Dagster asset graph are the inputs, and its DuckLake table is the output.
- It only reads what the materialization already carries: `dagster/column_schema` (schema facet), `dagster/row_count` (output statistics facet), `dagster/column_lineage` (column lineage facet) and the asset `kinds` (job type facet). `DuckLakeIOManager` now attaches row count and schema automatically; column lineage comes from `TableColumnLineage` metadata, which the planned `@track_lineage` decorator will fill.
- No data values: other metadata (previews, sample rows, run config) is never copied, so events contain job and dataset metadata only, no patient data.
- Naming: jobs use the node namespace (`OPENLINEAGE_NAMESPACE`, from `lineage_namespace` in `pluginlake.toml`) and the asset key (`omop/person`). Datasets use namespace `ducklake` and the DuckLake table reference (`ducklake.omop.person`), produced by the same `asset_key_to_table_ref` helper that `DuckLakeIOManager` uses to name tables, so dataset names in Marquez match the catalog (`/api/v1/catalog/tables`).
- Emission is best-effort and happens after the run has finished, so it never fails a run. When Marquez is unreachable the sensor logs one warning and skips the remaining events of that run (they are not replayed); a rejected event is logged as a warning and skipped. Each event gets at most one retry (`PLUGINLAKE_LINEAGE_RETRIES`).
- Configuration lives in `pluginlake.core.lineage.config`: `OPENLINEAGE_URL` (off while unset), `OPENLINEAGE_NAMESPACE`, and `PLUGINLAKE_LINEAGE_*` for the rest. With `lineage = true`, `pluginlake up` sets `OPENLINEAGE_URL=http://marquez:5000` and `OPENLINEAGE_NAMESPACE` on the Dagster service.

Where pluginlake deliberately differs from srdp:

| Topic | srdp | pluginlake | Reason |
|---|---|---|---|
| Marquez database | Separate database and role on the shared PostgreSQL, created by a setup job | Separate `marquez-db` container in the `lineage` profile | Keeps the optional service fully self-contained; no change to the core database when lineage is off |
| UI access | Behind Traefik with Zitadel SSO (oauth2-proxy) | Host loopback only | The station has no SSO proxy yet; access control follows Nuts/DSP (ADR-006, ADR-008) |
| Sensor registration | Each project registers the sensor in its own `definitions.py` | Core adds it once to the merged code location | Projects plug in through the manifest (ADR-009) and should get lineage for free |
