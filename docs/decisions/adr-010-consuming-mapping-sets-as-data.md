# ADR-010: Consuming sssom-rosetta mapping sets as data

**Status:** Proposed
**Date:** 2026-09-15

## TL;DR

**What this ADR decides:**

How pluginlake ingests the curated SSSOM mapping sets produced by `sssom-rosetta`, and what changes inside pluginlake once they are available.

| Question | Decision |
|---|---|
| Code dependency or data? | **Data.** A pinned release artifact loaded into DuckLake. No Python dependency on `sssom-rosetta`. |
| Where does it land? | `ducklake.rosetta.*`, via a `@multi_asset` and the existing `DuckLakeIOManager` |
| How is a new release detected? | **A sensor modelled on `omop_vocab_sensor`** |
| Custom IO manager? | **No.** SSSOM is tabular; the asset key path already resolves to `catalog.schema.table` |
| Dagster resource for CURIE lookup? | **Deferred** until a concrete call site exists |
| What replaces hand-maintained mapping knowledge? | `FHIR_TO_OMOP_TABLE` is **generated** from the mapping set |
| Who owns concept-level lookup? | **pluginlake.** `ducklake.omop_vocab` stays the system of record |
| Declared lineage | Consumed as the declaration behind ADR-007's opaque path, **amending ADR-007** |

**Prerequisite:** `sssom-rosetta` must publish mapping sets as immutable release artifacts before any of this is buildable.

## Context

`sssom-rosetta` curates SSSOM mapping sets between information models (OMOP CDM, ONZ-G, and on its roadmap FHIR).
It has decided (its ADR-0001) to distribute those as immutable, versioned release artifacts rather than as a service, and states in its interface contract that it has no stable Python API, runs no service, and takes no dependency on any consumer.

pluginlake is the intended consumer.
Three facts about the current codebase make this more than a new data source:

- [src/pluginlake/fhir/translator_registry.py](src/pluginlake/fhir/translator_registry.py) hand-maintains `FHIR_TO_OMOP_TABLE`, a dict expressing which FHIR resource type lands in which OMOP table.
  That is mapping knowledge, typed out a second time in a third repository, and it is already consumed in three places ([assets/fhir_sensor.py](src/pluginlake/assets/fhir_sensor.py), [api/services/fhir_ingestion.py](src/pluginlake/api/services/fhir_ingestion.py), [api/routers/fhir_statistics.py](src/pluginlake/api/routers/fhir_statistics.py)).
- `ducklake.omop_vocab` already holds `concept`, `concept_ancestor`, and `source_to_concept_map`, with `map_source_code` in [src/pluginlake/omop/vocabulary_queries.py](src/pluginlake/omop/vocabulary_queries.py).
  The "vocabulary backend" on `sssom-rosetta`'s roadmap therefore already exists here, in relational form.
- ADR-007 classifies `fhir_to_omop_tables` as an **opaque** asset and proposes that an engineer hand-writes its column mapping into a `@track_lineage` argument.
  `sssom-rosetta` publishes an OpenLineage column-lineage facet derived from the same reviewed mapping rows, which is the same correspondence from a reviewed source.

The ingestion pattern is not new either.
`OMOPSettings.vocabulary_url` ([src/pluginlake/omop/config.py](src/pluginlake/omop/config.py)) points at a GitHub release asset on a pinned tag, `download_and_extract` fetches it, `omop_vocabulary_tables` loads it, and `omop_vocab_sensor` triggers on change.
Mapping sets have the same distribution shape.

## Options considered

### Option A: Depend on `sssom-rosetta` as a Python package

Add it as an optional extra pinned to a git SHA, the way `plugin-rosetta` is consumed today.

| Criterion | Assessment |
|---|---|
| Effort | Low initially. |
| Coupling | Creates a dependency edge on a project that explicitly disclaims a stable Python API, stable module paths, and stable signatures. |
| Version resolution | Python version coupling and transitive conflicts, for content that is a few hundred rows of tabular data. |
| Queryability | Mapping rows arrive as Python objects, not as a table that can be joined against `ducklake.omop_vocab` in one query. |

**Verdict: rejected.** The interface contract makes the package a moving target on purpose, and the payload is tabular data that belongs in the catalog.

### Option B: Vendor the mapping CSV into pluginlake

Copy the curated rows into this repository.

| Criterion | Assessment |
|---|---|
| Effort | Lowest. |
| Reproducibility | No `mapping_set_version` to pin against; the copy silently drifts from the reviewed source. |
| Review | Mapping changes bypass the domain-expert review that is the entire value of `sssom-rosetta`. |

**Verdict: rejected.** This is the failure mode `FHIR_TO_OMOP_TABLE` already demonstrates.

### Option C: Load a pinned release artifact as a DuckLake asset

A `RosettaSettings` with a pinned `mapping_set_url`, a `@multi_asset` emitting `AssetKey(["rosetta", "<name>"])`, and a sensor modelled on `omop_vocab_sensor`.

| Criterion | Assessment |
|---|---|
| Effort | Low. The OMOP vocabulary path is the same pattern, already working. |
| Coupling | None. No import, no version resolution, no Python version constraint. |
| Queryability | `ducklake.rosetta.*` joins against `ducklake.omop_vocab.concept` in a single query. |
| Lineage | Dagster asset lineage for free; the mapping set becomes a visible upstream of everything derived from it. |
| Reproducibility | The pinned URL carries `mapping_set_id` and `mapping_set_version`, which ADR-009 requires on every derived response. |

**Verdict: adopted.**

### Option D: Query `sssom-rosetta` over an API at runtime

`sssom-rosetta` runs no service, and ADR-007 constraint 5 records that data stations run under egress restrictions.
Not available, and would not be chosen if it were: a pinned artifact is reproducible and an endpoint is not.

**Verdict: rejected.**

## Decision

**Mapping sets enter pluginlake as data: a pinned release artifact loaded into `ducklake.rosetta.*` (Option C).**
pluginlake takes no code dependency on `sssom-rosetta`.

| Project | Consumed as | Dependency edge |
|---|---|---|
| `plugin-rosetta` | Code (translator classes) | Optional extra `fhir`, pinned to a git SHA |
| `sssom-rosetta` | Data (a released SSSOM/TSV or Parquet) | None |

### Integration seams

Four seams, in increasing order of intrusiveness.

**Seam 1: settings, asset, sensor.**
`RosettaSettings` with a pinned `mapping_set_url` and `mapping_set_version`, following `OMOPSettings.vocabulary_url`.
A `@multi_asset` emitting `AssetKey(["rosetta", "<name>"])` and a sensor modelled on `omop_vocab_sensor`.
Each submodule carries its own `config.py`, so `RosettaSettings` lives with the ingestion code rather than in the root settings.

**Seam 2: no custom IO manager.**
`DuckLakeIOManager` ([src/pluginlake/core/ducklake/io_manager.py](src/pluginlake/core/ducklake/io_manager.py)) already derives `catalog.schema.table` from the asset key path and accepts `pl.DataFrame | pl.LazyFrame`.
`["rosetta", "omop_onz_g"]` resolves to `ducklake.rosetta.omop_onz_g` and the schema is created on demand.
SSSOM/TSV is tabular, so a dedicated IO manager would be pure duplication.
The only case for one would be persisting the RDF rendering, which this decision does not do: the tabular rendering is the integration path and the Turtle is for inspection.

Read the Parquet rendering where available.
The SSSOM/TSV YAML header requires header-aware parsing before a query engine can read the table; the Parquet sidecar removes that step with types intact, and the TSV remains the canonical artifact for verification.

**Seam 3: a Dagster resource, only once lookup is needed.**
"Join this table" is an asset. "Resolve this one CURIE during execution" is a `ConfigurableResource`.
A resource hides whether the backing store is a local DuckLake table or a remote endpoint, which is the swap an eventual authenticated vocabulary service would require.
Not built before a concrete call site exists.

**Seam 4: validation attaches to an existing hook.**
[src/pluginlake/assets/omop.py](src/pluginlake/assets/omop.py) already calls `validate_table_concepts` and `write_audit_table` into `ducklake.omop_audit`.
Mapping-derived validation belongs there as a second validator writing to the same audit schema, not as a new pipeline.

### Generated registry

`FHIR_TO_OMOP_TABLE` is generated from the mapping set asset rather than hand-maintained, once the mapping set covers FHIR ⇄ OMOP.
Its three consumers keep their current interface; only the source of the dict changes.
Until `sssom-rosetta` publishes a FHIR axis, the hand-maintained dict stays, and this is recorded as the target state rather than an immediate change.

### Execution constraints travel as data

`sssom-rosetta` publishes machine-readable constraint tables alongside each mapping set: which transformations a `predicate_id` permits, and what a `mapping_cardinality` requires.
pluginlake reads them rather than restating them, because restated rules drift.

The practical value is specific.
The SEIN-OMOP review recorded in [docs/reference/repository-review-pluginlake-integration.md](docs/reference/repository-review-pluginlake-integration.md) found non-deterministic visit linkage: `row_number() over (partition by person_id, visit_start_date)` filtered to `rownum = 1` with no `ORDER BY` tie-break.
That is an `n:1` mapping where nobody was forced to state how the "one" is chosen.
A constraint table that knows the mapping is `n:1` turns a silent correctness bug into an explicit, required declaration.

### Declared lineage: an amendment to ADR-007

ADR-007 defines four lineage extraction paths and marks `fhir_to_omop_tables` as opaque, to be handled by a hand-written `@track_lineage` column mapping.

That declaration instead comes from the OpenLineage column-lineage facet published with the mapping set.
The facet is derived from the same constraint tables that govern execution, so lineage rules and execution rules cannot diverge.
It is a file travelling with the artifact, so it works under ADR-007's network isolation constraint with no outbound call.

Declared lineage complements runtime capture, it does not replace it:

- Where runtime capture works (`duck_lineage` on SQL, `Expr.meta` on Polars expressions), the declaration is a **cross-check**.
- Where runtime capture is structurally blind (opaque Python), the declaration is the **only** source.
- Where observed columns are not covered by the declaration, that is a **detectable divergence** between a mapping and its implementation, surfaced as an asset check.

ADR-007's constraint 2 ("runtime, not build-time") still holds: `can_subset=True`, `SELECT *`, and polymorphic FHIR data mean the actual column set is not knowable before materialisation, so a declaration can never be the only source of truth overall.

**Granularity caveat.** Today's mapping sets are class-level (`omop:Person` to `onz-g:PatientInCare`), which is a table edge, not a column edge such as `birthDate` to `year_of_birth`.
Interim declared lineage is therefore coarse, and distinguishing table edges from column edges depends on `subject_type`/`object_type` being authored upstream.
Coarse is still more than the opaque path has today, which is nothing.

### Vocabulary ownership stays here

pluginlake keeps ownership of the concept tables.
Concept lookup over millions of rows is what DuckDB is for, and `ducklake.omop_vocab` plus `map_source_code` already implement it.
`sssom-rosetta`'s merged vocabulary graph stays an internal authoring artifact and is not published, for licence reasons.

The consequence is that any concept-level lookup a mapping implies is served locally, from a vocabulary the station has licensed itself.
This is the same boundary ADR-009 enforces on the exposure side.

## Consequences

**Positive:**

- No dependency edge. `sssom-rosetta` can refactor its modules and `pluginlake` its asset keys, without either breaking the other.
- Mapping rows are queryable next to the concepts they reference, in one DuckDB query.
- Mapping knowledge exists once, in a reviewed artifact, instead of three times across three repositories.
- The opaque lineage path gains a reviewed, schema-validated source instead of a decorator argument.
- Drift between a mapping and its implementation becomes detectable rather than invisible.
- `mapping_set_id` and `mapping_set_version` are present in the catalog, which is what ADR-009 requires every derived response to carry.

**Negative / costs:**

- Mapping updates arrive at release granularity, not when a pull request merges upstream.
- Two artifacts (mapping set and execution recipes) must stay in sync; the observed-versus-declared asset check is the mitigation, not a guarantee.
- A new sensor and asset group to operate, with the same failure modes as the vocabulary path.
- Reading published constraint tables means parsing a format defined elsewhere, which can change with an upstream release.

**Prerequisite:** every seam depends on `sssom-rosetta` publishing release artifacts with a `mapping_set_version`.
Nothing here is buildable before that.

## Rollout

| # | Change | Depends on |
|---|---|---|
| 1 | `RosettaSettings` plus a `@multi_asset` loading the pinned artifact into `ducklake.rosetta.*` (seam 1) | Upstream release artifacts |
| 2 | Sensor modelled on `omop_vocab_sensor`, triggering on a new pinned version | 1 |
| 3 | Mapping-derived validation alongside `validate_table_concepts`, writing to `ducklake.omop_audit` (seam 4) | 1 |
| 4 | Feed the published lineage facet into ADR-007's opaque path, replacing hand-written `@track_lineage` arguments | 1 |
| 5 | Asset check comparing observed lineage against the declaration | 4 |
| 6 | Generate `FHIR_TO_OMOP_TABLE` from the mapping set asset | A published FHIR ⇄ OMOP axis upstream |
| 7 | Enrich `/columns` and the lineage endpoints from `ducklake.rosetta.*` (ADR-009) | 1 |
| 8 | Dagster resource for CURIE resolution (seam 3) | A concrete call site; not before |

## Open questions

- Which mapping sets does a station load: all published sets, or a configured subset per deployment?
- What happens when a pinned mapping set version is upgraded and existing derived tables were built against the previous one? Does the sensor trigger a full rebuild?
- Does the constraint-table format warrant a small parsing helper in `pluginlake/utils/`, or is it simple enough to read inline in the asset?
- Should the asset check in step 5 fail a materialisation or only warn, and does that differ between a station and the hub?

## Related decisions

- [ADR-001](adr-001-asset-architecture.md): asset architecture and extensibility; the mapping set is another asset group.
- [ADR-003](adr-003-ducklake-data-catalog.md): DuckLake as the catalog; `ducklake.rosetta.*` follows its conventions.
- [ADR-007](adr-007-column-level-lineage.md): **amended** by the declared lineage section above.
- [ADR-009](adr-009-semantic-metadata-exposure.md): how the loaded mapping sets are exposed, and the licence boundary on that exposure.
- [ADR-011](adr-011-relational-mapping-execution.md): which engine executes the transformations these mappings describe.

In `sssom-rosetta`: ADR-0001 (versioned artifacts), ADR-0002 (two layers and the four seams above), ADR-0004 (declared lineage), and the interface contract.
