# ADR-011: Relational mapping execution, no graph engine in the data station

**Status:** Proposed
**Date:** 2026-09-15

## TL;DR

**What this ADR decides:**

Which engine executes the transformations that mapping sets describe, and whether a data station needs a graph or SPARQL engine alongside DuckLake.

| Question | Decision |
|---|---|
| Execution engine | **DuckDB and Polars, vectorised.** No per-row CPython loop. |
| Triplestore (QLever) in a station | **No.** Deferred with an explicit trigger. |
| DuckPGQ (SQL/PGQ over DuckDB) | **Deferred**, pending a measured traversal need and a spike |
| Hierarchy queries | **Materialised `CONCEPT_ANCESTOR`**, not runtime traversal |
| RDF in pluginlake | **Not an integration format.** Mapping sets arrive tabular (ADR-010). |
| Who keeps the graph? | `sssom-rosetta`, for authoring and validating mappings. Not pluginlake. |

**Second payoff:** vectorising `fhir_to_omop_tables` moves it off ADR-007's opaque lineage path, so throughput work and lineage work are the same work.

## Context

`sssom-rosetta` splits semantic correspondence (what maps to what) from execution plans (how to transform a row), and its ADR-0003 decides that mapping *authoring* stays on an embedded RDF graph.
It says nothing binding about pluginlake, because execution is pluginlake's concern.
This ADR decides it here.

The question is real because RDF and SPARQL are the natural shape for reasoning about ontology mappings, and mapping sets arrive from a project that reasons about them that way.
The data those mappings are applied to is columnar and lives in DuckLake.

### How mappings are executed today

[src/pluginlake/assets/fhir.py](src/pluginlake/assets/fhir.py) reads a DuckLake table into Polars and then loops in CPython:

```python
raw_df = conn.sql(f"SELECT json_data FROM {raw_ref}").pl()
translator = get_translator(fhir_type)
for row in raw_df.get_column("json_data").to_list():
    record = orjson.loads(row)
    translated = translator.translate_record(record)
```

Storage and transport are columnar; the transformation unpacks a DataFrame into dicts and repacks it.
That is neither a graph problem nor a vectorised one.
In the same repository, `omop_clinical_tables` already validates concepts with a DuckDB join against `ducklake.omop_vocab`, so the fast path exists, just not for the mapping step.

### The governing performance fact

OMOP ships the transitive closure of the `Is a` hierarchy as `CONCEPT_ANCESTOR`.
Once materialised, "find all descendants of this concept" is an indexed join rather than a traversal.
That removes precisely the advantage a graph engine is bought for, and the choice is paradigm-independent: it helps SQL and a triplestore equally, and it is the single largest hierarchy-performance decision available.

### Deployment shape

pluginlake is embedded: DuckLake is files, Dagster orchestrates, no database server runs.
In a federated deployment, any server process is repeated per data station, inside hospital networks with strict egress controls and local operational constraints (ADR-006, ADR-008).
A second store beside `ducklake.omop_vocab` also means two systems of record and two versioning schemes.

## Options considered

### Option A: Relational execution on DuckDB and Polars

Execute transformations as SQL or Polars expressions, keep the pre-materialised closure, use recursive CTEs for the rare remainder.

| Criterion | Assessment |
|---|---|
| New infrastructure | None. Both engines are already in-process. |
| Edge metadata | `CONCEPT_RELATIONSHIP` carries `valid_start_date`, `valid_end_date`, `invalid_reason`. In SQL these are columns. |
| Hierarchy | Indexed join over the materialised closure. |
| Lineage | SQL is covered by `duck_lineage`; Polars expressions by `Expr.meta` (ADR-007). |
| Weakness | Ad hoc multi-hop exploration across ontologies stays awkward. |

### Option B: A triplestore (QLever) beside DuckLake

| Criterion | Assessment |
|---|---|
| New infrastructure | A server process, per data station, in a federated deployment. |
| Edge metadata | RDF 1.1 cannot put properties on an edge. Validity dates need reification (roughly 4 to 5 times the triples, and verbose SPARQL) or RDF-star. |
| Two truths | `ducklake.omop_vocab` is the system of record; a triplestore beside it needs synchronisation and a second versioning scheme. |
| Gain | Traversal, which the materialised closure already serves. |

### Option C: Embedded SPARQL (maplib) for execution as well as authoring

One query language across authoring and execution.

| Criterion | Assessment |
|---|---|
| RDF-star | Not supported by maplib, so OMOP's edge validity columns cannot be carried. |
| Conversion cost | Pushing columnar row data through a triple model to transform it adds a conversion on both ends. |
| Gain | Uniformity, not performance. |

### Option D: DuckPGQ, a graph view over the existing tables

The [DuckPGQ](https://duckdb.org/community_extensions/extensions/duckpgq) community extension implements SQL/PGQ (SQL:2023) over existing DuckDB tables:

```sql
CREATE PROPERTY GRAPH g
  VERTEX TABLES (concept)
  EDGE TABLES (concept_relationship
    SOURCE KEY (concept_id_1) REFERENCES concept (concept_id)
    DESTINATION KEY (concept_id_2) REFERENCES concept (concept_id) LABEL rel);
```

| Criterion | Assessment |
|---|---|
| New infrastructure | None. A graph view over tables: no second store, no synchronisation, no extra process. |
| Edge metadata | Stays columnar. |
| Extras | Ships `pagerank`, `weakly_connected_component`, `local_clustering_coefficient`, `reachability`, `shortestpath`. |
| Maturity | Community extension, not core; maintainers describe it as part of an ongoing research project at CWI with features still under development. |
| Unknown | Whether `CREATE PROPERTY GRAPH` works over an **attached DuckLake catalog** is unverified. A negative answer closes the option outright. |
| Scope | A labelled property graph replaces recursive CTEs, not an RDF authoring graph. |

## Decision

**Transformations are executed relationally, on DuckDB and Polars (Option A).**
**No graph or triplestore process runs in a data station.**

- Mapping sets arrive tabular and are loaded into `ducklake.rosetta.*` (ADR-010). The Turtle rendering upstream is for inspection; RDF is not an integration format here.
- Hierarchy questions use the materialised `CONCEPT_ANCESTOR` rather than runtime traversal.
- The authoring-side graph stays in `sssom-rosetta`. pluginlake does not build a second one.
- Option C is rejected for execution: no RDF-star, and a round trip through a triple model for no gain.

### Deferral triggers

Revisit only when one of these is a real requirement rather than a preference:

| Option | Trigger |
|---|---|
| DuckPGQ | A measured traversal workload the materialised closure cannot serve, **and** a timeboxed spike confirming it works over a DuckLake catalog. |
| QLever | SPARQL `SERVICE` federation against external graphs, an integrated full-text index, or a graph beyond the in-memory ceiling of the authoring engine. |
| LadybugDB | Not before its ecosystem maturity at OMOP scale is comparable to the alternatives. |

### Where the throughput actually is

Choosing a relational engine only pays off if the pipeline uses it as one.
Six places where it currently does not, in descending order of expected gain.
These are the substance of this decision, not the engine label.

**1. The assets bypass the IO manager's load path.**
`DuckLakeIOManager.load_input` returns `self._conn.sql(...).pl(lazy=True)`: a LazyFrame with projection and filter pushdown into DuckDB, and DuckLake file pruning.
No asset uses it.
`fhir_to_omop_tables` and `omop_clinical_tables` both declare `deps=[AssetKey(...)]`, a dependency that does not load, then open their own connection and read eagerly with `SELECT *`.
Moving from `deps=` to real asset inputs restores laziness and pushdown with no new infrastructure.

**2. The transformation is a per-row CPython loop.**
See the context section. DuckDB's native JSON functions can extract fields in SQL, removing the Python objects entirely.

**3. Schema inference scans the whole dataset.**
`pl.DataFrame(all_rows, infer_schema_length=None)` reads every row to infer types, while the OMOP schema is already known from the generated models.
Passing an explicit schema removes a full pass.

**4. Every materialisation rewrites the whole table.**
`handle_output` issues `CREATE OR REPLACE TABLE ... AS SELECT * FROM _data`.
For a station ingesting continuously this is the ceiling.
Dagster partitions plus DuckLake copy-on-write allow incremental loads.
This is an architectural choice, best made while the surrounding design is still moving.

**5. A full scan per write, for a log line.**
`handle_output` runs `SELECT COUNT(*)` over the table it just wrote, purely to log the row count.

**6. Validation materialises the table in Python.**
`validate_table_concepts` takes a `pl.DataFrame`; an anti-join against `ducklake.omop_vocab.concept` does the same work in SQL and writes straight to `omop_audit`.

None of these require anything from `sssom-rosetta`.
Mapping sets are hundreds of rows and are not a throughput concern.

### Vectorising also buys lineage

Observations 1 and 2 have a second payoff that is easy to miss.
ADR-007 classifies `fhir_to_omop_tables` as **opaque**: it manipulates Python dicts, so neither `duck_lineage` nor `Expr.meta` observes anything, and column lineage has to be hand-declared.

Moving that asset onto Polars expressions drops it into ADR-007's semi-automatic path where `Expr.meta` works; moving it onto SQL drops it into the fully automatic path `duck_lineage` covers.
The throughput work and the lineage work are the same work.

Under ADR-010, declared lineage from the mapping set is the only source while the asset stays opaque, and becomes a cross-check once it is not.

## Consequences

**Positive:**

- No new process, deployment target, or store is introduced into a federated, embedded architecture.
- Edge validity (`valid_start_date`, `valid_end_date`, `invalid_reason`) stays representable as plain columns.
- One system of record for concepts, with one versioning scheme.
- Removing the CPython loop is almost certainly the largest available speedup and needs no new technology.
- The opaque lineage path shrinks as assets are vectorised, which reduces what has to be declared.

**Negative / costs:**

- Ad hoc multi-hop exploration across ontologies stays awkward in SQL, and is served by the authoring-side graph rather than by the execution engine.
- External linked-data federation remains out of reach without revisiting this.
- The decision rests on measurements of graph building and querying done upstream, not on transformation throughput measured here. That measurement does not exist yet, which is why it is rollout step 1.
- Incremental materialisation (observation 4) is a real architectural change, not a tuning fix.

## Rollout

| # | Change | Note |
|---|---|---|
| 1 | Measure current transformation throughput in `assets/fhir.py` | Every step below is justified against this number, and it may make some of them unnecessary |
| 2 | Switch `deps=` to real asset inputs so the lazy, pushdown-capable load path is used | Observation 1 |
| 3 | Replace the per-row CPython loop with Polars expressions or SQL | Observation 2; also moves the asset off ADR-007's opaque path |
| 4 | Pass explicit schemas instead of inferring over the full dataset | Observation 3 |
| 5 | Drop the `SELECT COUNT(*)` log scan; move concept validation to an anti-join | Observations 5 and 6, both cheap |
| 6 | Decide incremental versus full-rewrite materialisation | Observation 4 |
| 7 | Use the materialised `CONCEPT_ANCESTOR` for hierarchy questions instead of traversing | |
| 8 | Timeboxed DuckPGQ spike, only if step 7 leaves a traversal workload unserved | First question: does it work over a DuckLake catalog? |

## Open questions

- What is the actual throughput of `fhir_to_omop_tables` today, and which of steps 2 to 6 does that number justify?
- Can every FHIR resource type be extracted with DuckDB JSON functions, or do the polymorphic types need a Polars expression fallback?
- Does incremental materialisation interact with ADR-007's lineage capture, given that `duck_lineage` observes per query?
- Is there any traversal workload today that the materialised closure does not serve, or is the DuckPGQ deferral purely theoretical?

## Related decisions

- [ADR-001](adr-001-asset-architecture.md): Dagster assets with Polars/DuckDB, not dbt SQL models.
- [ADR-003](adr-003-ducklake-data-catalog.md): DuckLake as the catalog, embedded, no server process.
- [ADR-007](adr-007-column-level-lineage.md): the four lineage extraction paths this decision moves assets between.
- [ADR-010](adr-010-consuming-mapping-sets-as-data.md): how the mapping sets executed here arrive.

In `sssom-rosetta`: ADR-0002 (two layers), ADR-0003 (the authoring/execution engine split), ADR-0004 (declared lineage).
