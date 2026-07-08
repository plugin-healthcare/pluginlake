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

```
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

For unified lineage collection, all environments should run a local OpenLineage HTTP endpoint so all three emission paths converge at the same backend. Whether Marquez or a simpler receiver is the right choice is an open question.

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
- Stand up a local OpenLineage HTTP endpoint (Marquez or lighter alternative)

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
