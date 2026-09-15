# ADR-009: Exposing semantic metadata (mapping sets) to internal and external consumers

**Status:** Proposed
**Date:** 2026-09-15

## TL;DR

**What this ADR decides:**

How a consumer finds out what a column *means* and which mapping produced it, given that the mapping authoring system (`sssom-rosetta`) is internal and build-time only.

| Question | Decision |
|---|---|
| Where does semantic metadata surface internally? | **The existing catalog and lineage endpoints**, enriched from `ducklake.rosetta.*` |
| Do we build a dedicated mapping API? | **No, deferred** until the existing surfaces prove insufficient |
| Where does it surface externally? | **The DSP catalog entry** (pre-contract discovery, ADR-008) |
| What must never be exposed through it? | **Vocabulary content** (SNOMED CT, OMOP concept names, DHD thesauri): licence-gated |
| What must every mapping-derived response carry? | `mapping_set_id` and `mapping_set_version` |

**Leading force:** the licence boundary, not API ergonomics.

## Context

`sssom-rosetta` produces versioned SSSOM mapping sets at build time and is deliberately not externally reachable.
Its artifacts land in pluginlake as queryable tables (`ducklake.rosetta.*`).
The open question is which pluginlake surface carries the semantic meaning those mappings encode.

This fits the existing architecture rather than challenging it.
ADR-005 already states the rule:

> No downstream service (Dagster, DuckLake, storage) is exposed directly.

Dagster, DuckLake, and storage are all internal and FastAPI is the only external surface.
`sssom-rosetta` being internal is the norm, not an exception.
The question reduces to: which FastAPI surface carries semantic metadata, and what does the DSP catalog entry expose to parties who have not yet negotiated a contract?

### Two audiences that must not be conflated

| | Build-time distribution | Run-time exposure |
|---|---|---|
| Audience | Pipelines, developers | Data consumers, researchers, other stations |
| Question | "Give me the mapping set" | "What does this column mean, and which mapping produced it" |
| Form | Immutable file at a pinned version | API response |
| Owner | `sssom-rosetta` | pluginlake (this ADR) |

The first must be pinnable and reproducible, the second must be current and authorised.
A single mechanism serving both gets the worst of each: an API that is not reproducible and an artifact that is not authorised.

### The licence constraint

Mapping sets are CC0 and may be exposed freely.
The vocabularies they reference are not: SNOMED CT requires an affiliate licence, the OMOP vocabulary bundle requires an Athena account, and the DHD thesauri carry their own terms.

An endpoint that returns mapping metadata and helpfully joins the concept name in from `ducklake.omop_vocab` distributes licence-gated content to a caller who may not hold that licence.
This is the most likely way the design goes wrong, precisely because it looks like an improvement.

Labels authored in `sssom-rosetta` (`subject_label`, `object_label`, `comment`) are safe.
Concept names and descriptions read from vocabulary tables are not.

## Options considered

### Option A: Enrich the catalog API

`api/routers/catalog.py` serves `/schemas`, `/tables`, and `/columns`, all read straight from `information_schema`: names and types, no meaning.
Once mapping sets are queryable in `ducklake.rosetta.*`, `/columns` can report what a column stands for, under which predicate, and with what confidence.

| Criterion | Assessment |
|---|---|
| New infrastructure | None. A join against an existing catalog query. |
| Fit with audience | Direct: the consumer asking "what is this column" is already calling `/columns`. |
| Licence risk | Contained, provided the join stops at `rosetta.*` and never reaches `omop_vocab`. |
| Gap | Answers "what does it mean", not "which mapping produced it, on whose authority". |

### Option B: Implement the lineage endpoints ADR-005 already specifies

```
GET /api/assets/{key}/lineage
GET /api/assets/{key}/lineage/columns
```

These are decided in ADR-005 but not yet built.
Fed by observed lineage (`duck_lineage`, ADR-007) plus the declared lineage facet from `sssom-rosetta`, they answer the provenance half of the question.

| Criterion | Assessment |
|---|---|
| New infrastructure | None in principle: the endpoints are already specified and the lineage store is ADR-007's scope. |
| Fit with audience | Answers "which mapping produced this column, and on whose authority". |
| Dependency | Requires declared lineage to be emitted alongside observed lineage. |

### Option C: Extend the Dagster metadata proxy

`api/routers/assets.py` already pulls `TableSchemaMetadataEntry` (column name, type, description, constraints) over Dagster's GraphQL API.
Adding `TableColumnLineage` to the same query extends an existing mechanism rather than introducing a new one, and surfaces column provenance in the operator-facing views.

| Criterion | Assessment |
|---|---|
| New infrastructure | None. One additional fragment in an existing GraphQL query. |
| Fit with audience | Operators and developers, not external consumers. |
| Limitation | Bound to what assets emit into the Dagster event log. |

### Option D: A dedicated mapping endpoint

Something like `/api/v1/mappings` served from `ducklake.rosetta.*`.

| Criterion | Assessment |
|---|---|
| New infrastructure | A new resource, its own models, its own authorisation rules. |
| Cost | A separate resource for something that is also a property of a column doubles the surface and splits the authorisation logic across two places. |
| When it becomes right | If consumers need to browse or diff mapping sets independently of any column, which is not a demonstrated requirement today. |

### The external surface: the DSP catalog

This is the part with no prior design.
ADR-008 adopts the Eclipse Dataspace Protocol, which defines three phases: catalog browsing, contract negotiation, and data transfer.

Catalog browsing is *pre-contract* discovery: an external party inspects what a station offers before any access is negotiated.
That is exactly the moment semantic meaning is needed, which places mapping metadata in the DSP catalog entry rather than behind the contract boundary.

ADR-008's ODRL permissions are column-scoped:

> "user X may read columns A,B of dataset Y where region=NL"

Column permissions and column mappings operate on the same identifiers.
A researcher requesting access to "diagnoses" needs to know which columns that is semantically, and the station evaluating the permission works on those same names.
Declared column lineage is the bridge between the two.

## Decision

**Semantic metadata is exposed through the existing catalog and lineage surfaces (Options A, B, and C), not through a parallel mapping API (Option D).**
**The DSP catalog entry carries mapping metadata for pre-contract discovery.**
**Vocabulary content is excluded from all of these by an explicit authorisation rule.**

Concretely:

1. `/columns` in `api/routers/catalog.py` is enriched with the mapping facts held in `ducklake.rosetta.*`: what the column stands for, under which predicate, with what confidence.
2. The lineage endpoints specified in ADR-005 are implemented and fed by both observed lineage (ADR-007) and the declared lineage facet from `sssom-rosetta`.
3. The Dagster metadata proxy in `api/routers/assets.py` adds `TableColumnLineage` to its existing GraphQL query.
4. The DSP catalog entry (ADR-008, Phase 1) includes mapping metadata per dataset and per column, available before contract negotiation.
5. A dedicated `/api/v1/mappings` resource is deferred until 1 to 3 demonstrably fall short.

### Authorisation rule: the licence boundary

Mapping-derived responses may include only fields authored in the mapping set itself: identifiers, predicates, confidence, `subject_label`, `object_label`, and `comment`.

Responses must not join, denormalise, or otherwise include content from vocabulary tables (`ducklake.omop_vocab` and equivalents) unless the caller's authorisation explicitly asserts the corresponding licence.
This rule is part of the ODRL enforcement layer in ADR-008, not an implementation detail of each endpoint.

### Reproducibility rule

Every response derived from a mapping set carries `mapping_set_id` and `mapping_set_version`.
Without them a consumer learns what was mapped but not which version was applied, and the answer is not reproducible.
This is a condition in the `sssom-rosetta` interface contract and a requirement on pluginlake's response models.

## Consequences

**Positive:**

- No new external surface. Every internal change is an extension of an endpoint that already exists or is already specified.
- Column permissions (ADR-008) and column mappings share one set of identifiers, so access requests can be expressed in semantic terms.
- Semantic discovery happens before contract negotiation, which is when an external party actually needs it.
- The licence boundary is enforced in one place rather than re-litigated per endpoint.

**Negative / costs:**

- The enriched `/columns` response grows and is no longer a thin pass-through over `information_schema`.
- Two lineage sources (observed and declared) must be reconciled into one response shape.
- Consumers wanting to browse mapping sets as first-class resources are not served until Option D is revisited.
- The licence rule constrains obvious usability improvements; joining a concept name in is a one-line change that must be prevented by design and by review.

**Dependency:** mapping sets must be queryable in DuckLake (`ducklake.rosetta.*`) before any of the four surfaces can be built.
This is `sssom-rosetta`'s first seam and is a hard prerequisite.

## The chain, end to end

```
sssom-rosetta (internal, build-time)
  -> release artifact at a pinned version
    -> ducklake.rosetta.* in pluginlake
      -> FastAPI: catalog, lineage, asset metadata
        -> DSP catalog entry for external parties
```

Every link is decided or planned; this ADR decides the last two.

## Open questions

- Which mapping fields belong in the DSP catalog entry, and how are they expressed in DCAT/ODRL terms?
- Does an external party see mapping metadata for all datasets, or only for those it could in principle negotiate access to?
- How is the vocabulary licence asserted in a credential, so the authorisation layer can lift the exclusion for callers that legitimately hold one?
- How are conflicting mappings (multiple mapping sets covering one column) presented, and is a single "preferred" mapping selected or are all returned?

## Related decisions

- [ADR-005](adr-005-fastapi-gateway.md): FastAPI as the only external surface; specifies the lineage endpoints.
- [ADR-007](adr-007-column-level-lineage.md): column-level lineage strategy, observed lineage via `duck_lineage`.
- [ADR-008](adr-008-dataspace-protocol-authz-authc-rbac.md): DSP catalog browsing, ODRL column-scoped permissions, enforcement layer.
- [ADR-010](adr-010-consuming-mapping-sets-as-data.md): how mapping sets reach `ducklake.rosetta.*`, which every surface here depends on.
- [ADR-011](adr-011-relational-mapping-execution.md): which engine executes the mappings exposed here.

In `sssom-rosetta`: ADR-0001 (artifact distribution), ADR-0002 (two layers, seam 1), ADR-0004 (declared lineage), and the "Redistribution" section of the interface contract.
