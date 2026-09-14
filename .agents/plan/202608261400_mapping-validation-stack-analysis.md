# Mapping and validation stack: first analysis

Date: 2026-08-26
Author: @yannick-vinkesteijn (with Copilot)
Status: Exploratory analysis. Input for an ADR, not a decision itself.
Companion to: `.agents/plan/20260826_mapping-validation-stack-exporation.md` (the raw opdracht).

## 1. What we are investigating

The concrete question from the opdracht is how we actually want to use Rosetta, FHIR2OMOP and nyctea together, so that we can scope the kwaliteitsregistratie project and give a new colleague a clear starting point.

Heart failure (NHR Hartfalen) is the likely use case.
The target data flow, stated in the opdracht, is:
a blood value is registered in the EPD, pulled in as a FHIR Observation (a codeable concept: SNOMED/LOINC code plus a numeric value), converted to an OMOP Observation or Measurement, and finally mapped with NHR-specific heart-failure logic (for example the bloedwaarde buckets in the handboek) into the codes the registry expects.

Three sub-questions fall out of that flow, and this document treats them as the real scope:

1. Positioning is about which layer each tool owns and where the seams are, and the goal is to avoid two tools doing the same job.
2. Build, adopt or contribute is the decision, for every external project (fhir2omop, Ariadne, SQL-on-FHIR, SSSOM), of whether we consume its spec, run its code, or contribute back.
3. The counter-argument is that a critic says to just do a direct extraction per registry, and we owe a defensible answer rather than a reflex.

Two steers landed while writing this, and they shape everything below:

- The OMOP datastation product owner chose the simple route over the SemWeb/RDF route. Everything tabular for now, with clear standards and werkafspraken so ETL pipelines are reusable between hospitals. The predicates we will actually use are `exactMatch`, `broadMatch` and `narrowMatch`.
- The architect considers OHDSI Ariadne important to include. The open worry is scalability and efficiency, because Ariadne is pandas-based and uses a SQL server.

Section 3.5 answers the Ariadne worry directly. It is the wrong worry aimed at the wrong layer, but it points at a real deployment decision.

## 2. How we position the stack

The single most useful framing is to split the problem into two planes.

The first is the design-time, or authoring, plane. Here humans and assistive tooling produce and curate the artifacts, meaning the terminology mappings, the registry logic, the ViewDefinitions and the schemas. This work runs occasionally, centrally, and on small data, because a vocabulary is millions of rows while a mapping set is only thousands. It is allowed to use heavier tools such as a database, embeddings or an LLM, because it is not on the hot path and it is not federated.

The second is the run-time, or application, plane. Here pluginlake applies those finished artifacts to patient data inside each hospital's data station. This work runs repeatedly, is federated, and operates on large data, so it has to stay lean. It uses Polars and DuckLake over Parquet, with no external services and no per-record LLM calls, and it stays deterministic and auditable.

The whole stack lines up cleanly against that split and against pluginlake's existing medallion plus late-binding model (already settled in `.agents/memory/viscosuite-integration-discussion.md`).

```
                     DESIGN-TIME (central, small data, occasional)
  +-------------------------------------------------------------------+
  | sssom-rosetta    terminology + registry code maps (SSSOM/maplib)  |
  |                  exact/broad/narrow predicates; NHR Hartfalen map |
  | discovery        source term to OMOP concept candidates; verbatim |
  | (Ariadne logic,  + vector search, human-curated; feeds authoring  |
  |  Polars/DuckDB)  as candidate SSSOM rows; LLM optional, off       |
  | fhir2omop spec   ViewDefinitions (structural flatten) + edge specs|
  |                  reference; ViewDefinitions run in DuckDB          |
  +----------------------------+--------------------------------------+
                               | published as versioned, tabular
                               | artifacts (mapping tables, schemas)
                               v
                     RUN-TIME (federated, large data, repeated)
  +-------------------------------------------------------------------+
  | pluginlake (Dagster + Polars + DuckLake)                          |
  |  landing -> bronze -> silver (FHIR CDM) -> gold (OMOP + registry) |
  |  sssom-rosetta maps applied as joins, never recomputed            |
  |  nyctea validates every layer as Dagster asset checks             |
  |  FHIR flattening via SQL-on-FHIR ViewDefinitions (to decide)      |
  +-------------------------------------------------------------------+
```

The rule that keeps this honest is that mappings are authored centrally and applied federated.
A mapping table is not patient data, so it can live in one governed place and be shipped to every hospital.
That single boundary is also what answers the Ariadne scalability worry.

A second framing matters as much as the first, and it is about ownership. Three of the projects are ours (pluginlake, nyctea and sssom-rosetta), so we can decide to make them production-ready on our own schedule, while the externals (fhir2omop and Ariadne) are single-maintainer alpha, so we cannot. This splits into two independent rules that are easy to conflate. Maturity risk is something ownership removes: between our three, code-level dependencies are acceptable because we control the release cycle, whereas the externals we depend on only for their data and standards, never for their code, so a bad upstream release is a stale file rather than a broken import. Deployment role is something ownership does not change: even though sssom-rosetta is ours, its graph and maplib machinery still stays off pluginlake's federated hot path, because a loaded graph per hospital is the wrong shape regardless of who wrote it. The practical consequence is that the mature core running in every data station is only pluginlake and nyctea, and everything else, ours or external, contributes authored artifacts behind a versioned contract.

sssom-rosetta is our mapping layer for concept and registry maps.
It owns the terminology and registry code mappings (which code means which concept, and which OMOP concept becomes which NHR code) as tabular SSSOM tables.
The product owner's tabular steer applies inside it: keep its SSSOM/TSV mapping tables and the exact/broad/narrow predicates, and defer the full ontology-graph product route, while keeping maplib internally, where it is the fast, lazy way to build and validate a table.

The FHIR-to-OMOP transform is not one job, it is three layers, and only the middle one is SSSOM:

1. Structural projection and light transform (which FHIR field lands in which OMOP column, plus unnest, cast, pick-a-coding). A SQL-on-FHIR ViewDefinition expresses this directly: each column is a FHIRPath `path` and a `name`, and the name can be the OMOP column. A plain explode plus rename plus cast is fully a ViewDefinition, run in DuckDB (the engine DuckLake already uses). Note this layer is a mapping decision, so it is conceptually rosetta's domain, but it is not SSSOM: SSSOM expresses concept-to-concept equivalence, not structural field maps. The open question is where the layer-1 specification lives: either the ViewDefinition column list is the field-map spec (pull upstream ViewDefinitions, no separate artifact, no manual transform), or we keep a separate declarative field map (FML from the HL7 IG, or a field-map table) and generate ViewDefinitions from it.
2. Concept resolution (source code to `concept_id`). A vocabulary JOIN driven by SSSOM tables in sssom-rosetta. FHIRPath cannot do external lookups, so this is never a ViewDefinition.
3. OMOP-shaping and registry business logic (Measurement-vs-Observation routing, fan-out or pick-one, NHR Hartfalen buckets, surrogate keys, eras). SQL or Polars in gold. Neither a ViewDefinition nor SSSOM.

The deciding line for layer 1 is exactly the simple-explode versus selective-transformation distinction: as long as the flatten is projection, unnest and cast, the ViewDefinition holds; the moment a field needs a vocabulary lookup or computed logic it leaves the ViewDefinition into layer 2 or 3, regardless. A ViewDefinition is FHIRPath-in-JSON, not SQL, so it needs a SoF engine (a DuckDB one such as fhir4ds, note AGPL-3.0, or FlatQuack, or a small in-house ViewDefinition-to-DuckDB-SQL compiler) to run it. Polars SQL cannot run a ViewDefinition (it is a dialect over DataFrames, not a FHIRPath evaluator); Polars is for the join steps after flattening.

## 3. Repo-by-repo overview

Maturity is scored qualitatively as low / medium / good, from evidence in each repo (tests, CI, packaging, docs).

### 3.1 pluginlake (ours, the run-time spine)

Purpose: the federated lakehouse and data station. Dagster-orchestrated ingestion of OMOP CDM CSV and FHIR R4 NDJSON, FHIR to OMOP translation, OMOP vocabulary validation, persisted to DuckLake, exposed through a FastAPI gateway and a Streamlit datastation UI.

Structure: `src/` layout. Assets and sensors in `assets/`, code-location wiring in `definitions/`, OMOP schemas and validation in `omop/`, FHIR loader and the translator seam in `fhir/`, storage and DuckLake IO manager in `core/`, gateway in `api/`.

Tech: Dagster (assets with `can_subset`, sensors, a custom DuckLake IO manager, declarative automation), Polars plus DuckDB compute, DuckLake catalog (Postgres metadata over Parquet), medallion layering (raw / processed / output mapped to DuckLake schemas).

Maturity: good. 268 test functions across 33 files, CI runs ruff plus `ty` plus pytest with coverage, strict lint and type config, 8 ADRs in `docs/decisions/`, a docs site.

Role: owns the entire run-time plane. Every other tool either feeds it an artifact or plugs into it as a translator or an asset check.

Key seams:
- `fhir/translator_registry.py` is the FHIR-to-OMOP mapping seam. Today it is limited and does not yet cover lab-value Observations (see the Measurement gap below). It should be driven by sssom-rosetta maps, or replaced by a SQL-on-FHIR flattening step.
- The Measurement gap on our critical path: lab and vital-sign Observations belong in the OMOP Measurement table, which is not built yet. Heart failure is a lab-value story, so Measurement is the first thing to add.
- No gold, registry-specific asset exists yet, and no terminology or registry mapping-table join exists. NHR Hartfalen logic has no home. This is the main build gap, and it is where sssom-rosetta plugs in.
- nyctea appears nowhere yet. Validation is hand-rolled in `omop/validation.py` and `omop/vocabulary_validation.py`.

### 3.2 nyctea (ours, the validation library)

Purpose: a Polars-based data-validation library with an extensible OOP validator architecture. Declarative schema (YAML, JSON or dict) of parsers (transformations) and checks (validations), with on-failure handling (raise, null, ignore), column synonyms, dtype coercion and a validation report. Explicitly positioned against Pandera, Patito, Dataframely and Great Expectations.

Tech: Polars only, built on LazyFrame and Expr. No pandas, no SQL, no external service. Config-driven rules resolved by name against a registry; validator implementations are code.

Maturity: medium and trending up, with an active push toward the first stable release. It has 178 tests, 7 CI workflows, a PyPI release, a docs site, ADRs and a hand-maintained changelog. It is still formally alpha at version 0.2.0b2. The most recent package review rated production readiness 2 out of 5, but that review predates the current work, because the correctness blockers it raised are now fixed on the working branch: frame parsers and checks are wired into the pipeline instead of being silently ignored, duplicate check names no longer overwrite each other, `on_failure` is enforced for check failures, and the report no longer claims failing rows are valid. What still stands between it and a stable release is that a legacy System A (the old engine and function registry, close to half the source) is still being rewritten and is excluded from type checking until it is removed, the CLI exists in source but is not yet installed as a command, and the built-ins are still thin at five column parsers and four column checks. It has a single maintainer.

Role: the validation plane across pluginlake's medallion. It is the natural replacement for the hand-rolled checks, and sssom-rosetta already uses it for columnar validation. nyctea plus sssom-rosetta is the golden combo the opdracht points at: validate then map, both in Polars-friendly tabular form, both config-driven.

### 3.3 sssom-rosetta (ours, the "Rosetta" of the opdracht: the single mapping layer)

This is the Rosetta the opdracht is about: the mapping tool that a critic's "just do direct extraction" argument is aimed at, and the place the NHR Hartfalen mapping should live. It is a gold mine that is not yet mature enough to rely on, and it is our one mapping layer.

Purpose: integrate the ontologies and vocabularies used in Dutch healthcare, with SSSOM as the tabular mapping interchange. It authors pairwise mappings (for example OMOP CDM to ONZ-G) and ingests the large terminologies (OMOP/Athena, DHD, SNOMED, LOINC). The principle is that a mapping endpoint must resolve in a loaded vocabulary before the mapping is accepted (referential integrity).

Tech: SSSOM TSV plus CSVW authoring, generated Pydantic models from the LinkML sssom-schema, and rdflib plus maplib graphs internally (the vocabulary merge handles about 19.8M triples). Exports to SSSOM/TSV, Turtle, Protege OWL and Gephi GEXF.

Maturity: low for production. A genuine gold mine of design thinking, but: no CI for tests, lint or typecheck; a single hard-coded mapping set threaded through the CLI, justfile and both workflows; no LICENSE file; alpha and forked dependencies; a Python-version mismatch between pyproject and CI; only 8 curated mappings so far. Adding a mapping set still requires code edits in three or four places, so it is not yet the onboarding process the opdracht wants: it is still development, not configuration.

Role, and what the tabular steer means for it: sssom-rosetta stays as the home for the concept and registry maps (layer 2 above), used tabular-first. Keep the SSSOM/TSV mapping tables and the `exactMatch` / `broadMatch` / `narrowMatch` predicates (these are already SSSOM's own predicates, so the steer and the tool agree), keep the CSVW-driven authoring, and keep the referential-integrity check. There is no performance reason to change the authoring internals, because the expensive part, assembling the OMOP ontology from Athena's CSVs, is done by maplib lazily on top of Polars and Arrow, which is why maplib already replaced rdflib for the 19.8M-triple OMOP export. The referential-integrity check itself is lighter than it looks: it resolves every `subject_id` and `object_id` and asks only whether each concept exists in the vocabulary, which is an endpoint-existence set-membership test. That test runs today as an rdflib graph-membership check (`resource_exists` in `mapping/validate.py`), but semantically it is a `WHERE concept_id IN (SELECT concept_id FROM concept)` semi-join, so it is portable to a tabular DuckDB check with no graph loaded, and the maplib graph earns its keep on the build and OTTR side rather than on this check. It is also a design-time authoring step that runs centrally and occasionally, which is exactly the plane where a loaded graph is allowed. The tabular-first steer governs the shipped artifacts and the run-time application, not the internals of authoring: the mapping sets ship as SSSOM tables and are applied in pluginlake as joins, while maplib and OTTR stay as the efficient way to assemble and validate the vocabulary behind that. What the steer defers is the full ontology-graph product route and the Protege and Gephi RDF exports, deferred rather than deleted. If we ever want the check to run against pluginlake's DuckLake concept table instead, sssom-rosetta already scans Athena's CONCEPT.csv tabularly, so that option stays open, but it is a convenience, not a fix. The surface production-readiness work (CI, packaging, a LICENSE) is necessary but not the hard part.

The deeper target for sssom-rosetta is to become a content-agnostic engine, with the content lifted out of the code. Today the opposite is true, because there is a Python module per vocabulary (`vocabulary/omop.py`, `dhd.py`, `loinc_snomed.py`, `snomed_international.py`, `rf2.py`) and a single mapping set threaded by name through the CLI, the justfile and the workflows, so adding a vocabulary or a mapping set means writing code. The package it wants to be separates four things from the engine and treats them as versioned data: the config, the schemas (the SSSOM and CSVW definitions), the vocabularies (each declared as a source with a format, a namespace and an OTTR template, rather than a bespoke module), and the mappings (the SSSOM content packs already in `mappings/`). The engine then does two generic jobs over whatever content it discovers. It builds artifacts, generating the canonical SSSOM/TSV and the optional RDF, OWL and Gephi outputs from the declared content, and it validates, checking that content for schema conformance and referential integrity. Both jobs are authoring: transform here means turning mapping content into interchange artifacts, not applying mappings to patient data, which stays pluginlake's run-time job as a Polars join. This is the same content-agnostic, registry-driven shape nyctea already has for tabular validation, which is why the two are a natural pair: sssom-rosetta can lean on nyctea for the tabular validation half and keep the mapping and vocabulary build as its own contribution. Reaching that shape is what turns "add a mapping" and "add a vocabulary" from development into configuration, and it is the real investment this repo needs.

What makes this worth building rather than deferring to the reference SSSOM toolkit is the OMOP-vocabulary awareness. The mapping-commons `sssom-py` library already parses, validates and converts SSSOM, so a suite that only did that would be redundant. sssom-rosetta's durable differentiator is that it resolves both ends of every mapping against the actual OMOP and ONZ-G vocabularies, so it catches mappings to concepts that do not exist or that a new vocabulary release retired, which is the most common real mapping error and something a vocabulary-agnostic validator cannot see. That OMOP-aware validation, together with the OTTR and CSVW vocabulary assembly, is the reason to have our own suite alongside `sssom-py` rather than instead of it, and it is exactly what a producer like Ariadne would run its output through.

The one thing sssom-rosetta does not cleanly do, and the biggest open question: the layer-1 structural field transform (Patient.birthDate to person.birth_datetime, and the Observation-to-Measurement routing). SSSOM expresses code-to-code and concept-to-concept equivalences, not field-level structural transforms, so this does not fit its table shape. As set out in section 2, the leaning answer is to run this as SQL-on-FHIR ViewDefinitions in DuckDB and keep sssom-rosetta for layers 2 and 3's concept and registry maps. The remaining choice is only where the field-map specification is authored: the ViewDefinition column list itself (pull upstream, simplest), or a separate declarative field map (FML from the HL7 IG) that generates the ViewDefinitions. The routing decision (Measurement vs Observation) is a layer-3 concern that also depends on a vocabulary lookup, so it lives in the pluginlake shaping step, not in a single ViewDefinition.

### 3.4 fhir2omop (external, lampadephoros (Health Samurai))

What it is: a FHIR R4 to OMOP CDM v5.4 mapping specification plus a two-stage ELT runtime. 33 field-level edges, 28 FHIR StructureDefinition profiles, ValueSets, 10 ConceptMaps, and 26 SQL-on-FHIR ViewDefinitions. TypeScript on Bun over PostgreSQL. Two stages: ViewDefinitions flatten raw FHIR JSONB into wide tables, then plain SQL joins onto the Athena vocabulary resolve concept ids. "Concept-id resolution is a JOIN, not a function."

Maturity and community: alpha, single author (heavily AI-assisted), 7 stars, last push 2026-07-09. Not a working group product. Apache-2.0. The real standards venue is the HL7 Vulcan FHIR-to-OMOP IG, which fhir2omop itself points to.

Why it is a goldmine anyway, and exactly which parts port:
- The Observation routing question we care about is solved here explicitly. Route by the OMOP domain of `Observation.code`, enforced as a FHIR profile ValueSet binding: if the code is in the Measurement value set, write Measurement, else try Observation. This is directly reusable design for our Measurement gap. See its `mapspec/profiles/Observation__measurement.profile.json` and the public debate in its issue #31.
- The `GAPS.md` document is the most valuable single file: fan-out vs pick-one per target table (Observation fans out, Measurement must pick one because `value_as_number` cannot be duplicated), the list of FHIR fields with no OMOP target (severity, complication, outcome, criticality: precisely the registry payload), timezone conventions, and the `*_source_concept_id` provenance inventory.

What does not port: the TypeScript server and UI, and 33 PostgreSQL-dialect SQL files with hand-tuned indexes over a 6.4M-concept vocab schema. It is SQL-join-centric by design; DuckDB is a far lower-friction target than Polars if we ever run its ViewDefinitions.

Verdict, now elevated. With no second mapping tool in the picture, fhir2omop becomes our primary external reference for the structural FHIR-to-OMOP layer, and its 26 SQL-on-FHIR ViewDefinitions are directly runnable JSON (Apache-2.0). Consume the spec (edges, profiles, ViewDefinitions, GAPS.md) as the design reference and a source of golden test cases, and reuse the ViewDefinitions if we take the SQL-on-FHIR flattening route. Do not port the TypeScript or PostgreSQL runtime. Encode the routing idea in sssom-rosetta's maps or in the pluginlake flattening step.

### 3.5 OHDSI Ariadne (external, the architect's pick)

What it is: a Python toolkit for mapping source terminologies to OHDSI standard concepts. Workflows for conditions, drugs and procedures. Pipeline: term clean-up, verbatim (lexical) matching, embedding vector search for candidates, LLM-assisted selection of the best standard concept, hierarchy matching for the rest, and evaluation against gold standards.

The distinction that places Ariadne correctly is authoring versus discovery. sssom-rosetta authors, meaning you give it a mapping you have already decided and it validates, records and exports it. Ariadne discovers, meaning that given thousands of raw source terms and no idea which OMOP concept each one is, it proposes ranked candidate concepts for a human to approve. That candidate-generation step is the laborious half of mapping, and sssom-rosetta has nothing for it, so the two are complementary rather than competing: Ariadne proposes, a human curates, and sssom-rosetta records and validates. It is worth being precise about what Ariadne is, because "unsupervised mapping generator" overstates it: the models are pretrained and used for retrieval, not learned from your data, and the workflow is human-in-the-loop and scored against gold standards, so it is an assisted suggestion engine in the same category as OHDSI Usagi.

Tech and the worry: pandas, SQLAlchemy, psycopg, pgvector, spacy, openai. Python 3.12+. Alpha, version 0.0.1, in the OHDSI org, authored by contributors close to the OHDSI Vocabulary workgroup, actively developed, Apache-2.0. The PostgreSQL dependency is not an application database and holds no patient data: it is only a vector index behind the pluggable `AbstractConceptSearcher`, storing the roughly 6.4M-concept vocabulary embeddings so the vector-search step can run nearest-neighbour queries. There is already a second implementation of that interface (`hecate_concept_searcher.py`), which is the evidence that the backend is meant to be swapped, so the Postgres server is fully replaceable rather than core.

The scalability worry is answered once you see what Ariadne is. It is a design-time concept-mapping discovery tool, not a run-time record processor. Its input is a list of source codes (thousands to tens of thousands of rows), its output is a flat table:

```
source_code, source_term, target_concept_id, target_concept_name, predicate, target_concept_id_b, predicate_b
```

with `predicate` in `{exactMatch, broadMatch}` (see its `evaluation/concept_selection_evaluator.py`). At tens of thousands of rows pandas is irrelevant to performance. The Postgres plus pgvector instance is a lookup index for a human curation loop, not an ETL engine. Nothing Ariadne produces requires Ariadne to run again: the finished mapping table is applied in pluginlake with Polars.

So the deployment rule is that the discovery step runs centrally, once, for curation, never per hospital and never on the hot path. Standing up Postgres, pgvector, spacy and an LLM key in every data station would be the actual mistake, and it is avoidable because a mapping table is not patient data.

The pipeline is modular, and the automated decision is a single, separable stage. Verbatim mapping does exact and normalized lexical matching with no LLM, no embeddings and no API key, and it returns concept ids or candidate lists deterministically. Vector search retrieves and ranks candidates but does not decide, and its embedding model can run locally or be skipped. The `llm_mapping` module is the only place a model actually picks a concept, and hierarchy parent selection is again deterministic, operating purely on OMOP concept ids. Ariadne even ships two separate evaluators, one for candidate retrieval (recall at k) and one for the LLM selection, which is the evidence that the search-only output is a first-class deliverable you can stop at.

We agree with Ariadne's approach and adopt it, and this is worth stating plainly because it is the substance of the alignment: the pipeline design, the candidate-then-curate workflow, the exact/broad/narrow predicates, the `AbstractConceptSearcher` interface, the recall-at-k evaluation methodology, and SSSOM as the contract are all reused as-is. The only open question is which parts run in our stack, and the reasoning there is deployment fit, not code quality. Even if Ariadne's code were flawless, pandas plus Postgres plus pgvector is the wrong shape for a lakehouse that has to run federated inside each hospital on Polars and DuckDB, so we reuse the logic and reimplement the plumbing in our stack rather than ship a second runtime, and we do it against Ariadne's own interfaces so it aligns with the upstream work rather than forking from it. Apache-2.0 makes this clean, and the reusable core is small and mostly deterministic. Four pieces port directly: term clean-up and normalization (lowercasing, punctuation removal, stemming) as Polars string operations; verbatim matching as a Polars join of the normalized source term onto OMOP concept names and synonyms; hierarchy parent-selection as joins on `concept_ancestor`; and the recall-at-k evaluation harness. The one genuinely new capability is the embedding vector search, and even that need not be heavy. Nearest-neighbour is not a Polars operation and laziness does not help it, but at OMOP scale, once the candidate set is filtered by domain, vocabulary and standard-only, exact brute-force is fast enough and needs no index and no server: a DuckDB `array_cosine_distance` with `ORDER BY ... LIMIT k` over the concept embeddings in DuckLake is exact, streamed and stays in-stack, and a numpy matmul is the equivalent in-Python option. Only if that ever proves too slow at scale do we reach for DuckDB's VSS extension (HNSW), which is still in-stack. We are not introducing a separate vector database. Either way the Postgres server disappears, and a `DuckDBConceptSearcher` slots into the same `AbstractConceptSearcher` seam Ariadne already defines. The LLM selection stays as an optional stage, off by default, since deterministic verbatim plus filtered vector candidates plus human review is the responsible path and matches the OHDSI Usagi workflow. This still maps cleanly onto the SSSOM contract, because a human or lexical exact match ships as `mapping_justification` `semapv:ManualMappingCuration` at high confidence, while an LLM pick would be a lower-confidence, differently justified row, so the no-LLM-by-default policy is enforceable in the mapping table itself.

Two directions stay genuinely open here, and the ADR should choose rather than this analysis pre-empting it. The first is where the rebuilt discovery logic lives. One option is a component or package sitting next to sssom-rosetta and feeding it candidate SSSOM rows; the other is building discovery directly into sssom-rosetta so that one suite does discovery, authoring, validation and export. The argument for one suite is coherence and a single codebase we control; the argument for two components is that discovery and authoring have disjoint, heavy dependency trees, discovery pulling an embedding model while authoring pulls maplib and rdflib, so folding them into one module makes anyone validating a TSV drag in the embedding stack. A middle option keeps them as separate components in one project with optional extras, so an install pulls only the half you use. The second open direction is the compute split within discovery, Polars versus DuckDB: the deterministic string and hierarchy work is natural in Polars or numpy, while the vector search and heavy joins are natural in DuckDB, and both run over the same DuckLake Parquet, so this is a per-step choice rather than a single pick.

The real risks, ranked, are these. The first is maturity and deployment fit rather than the soundness of the approach: Ariadne is alpha and install-from-source with thin tests, which is why we reuse its logic against our stack rather than depend on the package as a shipped runtime. The second is the LLM dependency, which is nondeterministic and costed, but with the stage optional and a local-model path available it is no longer a top risk, and any use of it needs a gold-standard regression gate. Scale is not among the top risks for how we would use it.

There is a convergence worth noticing here. Ariadne's output predicates are exactly the `exactMatch` / `broadMatch` / `narrowMatch` predicates the product owner chose, which are the SKOS predicates, which are the SSSOM predicate column, which are Level 2 of the SSSOM OMOP tutorial. Ariadne, our tabular steer, and SSSOM all converge on the same tabular contract:

```
subject_id, predicate_id (exact|broad|narrow Match), object_id,
mapping_justification, confidence, mapping_tool, author_id
```

Adopt that contract as the one interface between mapping authoring and mapping application. Then Ariadne, Usagi, hand curation and sssom-rosetta are all interchangeable producers of the same table.

There is also a contribution opening that falls out for free. The DuckDB searcher we build for our own rebuild implements Ariadne's own `AbstractConceptSearcher` interface, so the same code can be offered back to OHDSI to drop the Postgres requirement in Ariadne itself. That is optional and political, not a dependency: we build the searcher for ourselves regardless, and contributing it back is a low-cost way to stay aligned with OHDSI rather than forking away silently.

### 3.6 Candid engineering assessment (internal)

This section states the honest engineering assessment behind the positioning above, separate from the constructive framing used with external maintainers. Being critical of code and tool choices is legitimate and is how we hold our own standard; it is not a judgment of the people or of the ideas, and the two registers are kept apart on purpose. These are the lead developer's and this analysis's candid read.

sssom-rosetta (ours, so ours to fix):
- The content is baked into the code. There is a Python module per vocabulary and a single hardcoded mapping set threaded through the CLI, the justfile and the workflows, so adding a vocabulary or a mapping set means editing code in several places. This is the central design problem, not a cosmetic one.
- No CI, no LICENSE, alpha and partly forked dependencies, a Python-version mismatch between pyproject and CI, and only 8 curated mappings. It is neither production-grade nor cleanly distributable yet.
- The referential-integrity check is implemented as an rdflib graph-membership test, while it is semantically a set-membership check that a DuckDB semi-join would do faster and without loading a graph. maplib's speed only benefits the vocabulary build, not this check, so the graph is doing more work here than the check needs.
- The design thinking (OMOP-aware validation, OTTR, SSSOM-first) is genuinely strong; the packaging and the content-versus-code separation are the weak parts.

Ariadne (external):
- Pre-production maturity: alpha at version 0.0.1, install-from-source only, thin tests (8 files), a sandbox directory, broken type annotations, and black rather than the ruff we standardize on.
- Tool-choice mismatch for our context: pandas for the dataframe work, and Postgres with pgvector as the vector store when the vector step is a nearest-neighbour lookup that DuckDB does serverless and exact at this scale. A whole database server for an index is overkill for us.
- The LLM in the decision path is nondeterministic and costed, and we do not want a model making the final call by default.
- The design is good and is exactly what we reuse: the `AbstractConceptSearcher` seam, the evaluation harness, and the predicate and SSSOM alignment. The critique is stack fit and maturity, not the approach.

fhir2omop (external):
- A polyglot runtime we do not want to operate: TypeScript on Bun over PostgreSQL, single author, heavily AI-assisted, alpha.
- Its Stage-2 shaping is PostgreSQL-dialect SQL with hand-tuned indexes, not portable to us without rework.
- The DuckDB SoF engines that could run its ViewDefinitions include fhir4ds, which is AGPL-3.0, a licence to check before adopting.
- The content is the real value and is reusable (26 ViewDefinitions as Apache-2.0 JSON, GAPS.md, the routing profile); the runtime is not.

nyctea (ours):
- Still alpha at 0.2.0b2, single maintainer, roughly 47% legacy source excluded from type checking, the CLI not yet installed, and thin built-ins (5 parsers, 4 checks). Trending up, but not yet the validation backbone the pipeline needs, and we should be honest that leaning the whole validation story on it is a bet on our own follow-through.

Overall stack:
- Scenario A's real cost is a polyglot, multi-service estate (two Postgres instances, pgvector, Bun, spacy, maplib and rdflib alongside our Polars and DuckDB), which is an operations and security burden regardless of any single tool's quality. Our standard on the federated path is one language and one compute stack.

None of this blocks collaboration. It sets the bar: we align on ideas and interfaces, we hold our own line on stack and production-readiness, and we stay candid internally about both while keeping the maintainer-facing conversation constructive.

## 4. Scope against external projects and communities

Positioning us relative to the outside world, with a stance for each.

OHDSI and OHDSI Netherlands. OMOP is the analytics product and OHDSI is the community we must keep happy, because they own the vocabulary and the tool stack (Atlas, Achilles, DQD, HADES) and the EU networks (EHDEN, DARWIN-EU). The NL national node is led from Erasmus MC, and its leads very likely overlap with our own product owner. Stance: align with OHDSI standards (CDM 5.4, standard vocabularies, the SKOS mapping predicates), consume Ariadne, and offer the DuckDB-searcher contribution. Show OHDSI that a Polars and DuckLake lakehouse is a first-class OMOP citizen, not a competitor.

HL7 Vulcan FHIR-to-OMOP IG. This is the actual standards home for FHIR to OMOP transformation. Stance: track the IG as our upstream source of truth for the structural field maps; treat fhir2omop as one implementer's reading of it, not as the standard.

SQL-on-FHIR v2 (ViewDefinition). A HL7 standard (v2.1.0-pre, an STU 3 ballot in the Sept 2026 cycle) for portable tabular projections of FHIR via FHIRPath. DuckDB-based Python implementations exist (fhir4ds, FlatQuack); notably no Polars-native engine exists, and Polars SQL cannot run a ViewDefinition because it has no FHIRPath evaluator. Stance: this is the standards-blessed way to flatten FHIR into tables, it is exactly our silver-layer job, and it is the leaning choice for the structural transform. A ViewDefinition is FHIRPath-in-JSON, not SQL, so we run it with a DuckDB SoF engine (fhir4ds, which is AGPL-3.0, so check licence fit, or FlatQuack, or a small in-house ViewDefinition-to-DuckDB-SQL compiler), landing wide tables in the same engine DuckLake already uses. This lets us consume upstream ViewDefinitions as pinned JSON with no manual transform. Caveat: fhir2omop's ViewDefinitions cover only the flatten (Stage 1); the OMOP-shaping SQL (Stage 2: concept JOINs, fan-out, routing) is PostgreSQL and still needs porting to DuckDB or expressing as our own maps. A Polars-native ViewDefinition engine is a visible ecosystem gap and a possible contribution, but not something to build for its own sake.

SSSOM and Mapping Commons. SSSOM is a mature, tabular-first mapping standard (BSD-3, LinkML-based) with a first-party tutorial on enriching OMOP mappings in exactly three levels: prefix ids and add provenance, then use real predicates (`exactMatch` vs `broadMatch`), then add a confidence score. That tutorial is the blueprint for our tabular steer. Stance: adopt SSSOM as the on-disk format for every mapping table, at the level of maturity we need (the columns, the predicates, the provenance fields), without committing to the full RDF machinery. This keeps sssom-rosetta's good half.

The NHR and the "why not direct extraction" answer. The NHR is a physician-driven national cardiac quality registry. Today each centre extracts its own data against a yearly handboek (a per-registry data dictionary with mandatory and optional variables and delivery moments) and uploads it to MijnNHR. That is per-registry direct extraction, not a common data model. The honest cost-benefit:

- For the common-model route (ours): registration burden is a named national policy problem (NHR itself cites the balance of registratielast; "eenmalig vastleggen, meervoudig gebruik" is national policy). With 9 NHR registries times many centres times yearly handboeken, per-registry extraction cost is multiplicative; a CDM collapses it to source-to-CDM plus CDM-to-registry views. And OMOP unlocks the OHDSI analytics stack and EU networks.
- For the direct-extraction critic: semantic loss at the CDM boundary is real and documented (fhir2omop lists FHIR fields with no OMOP target: severity, complication, outcome, which are the registry payload for an outcomes registry). Many registry variables are physician-adjudicated and not EHR-derivable at all. And a CDM adds a lossy hop over immediate source provenance.

Our defensible position: do not frame it as CDM versus extraction. The common model earns its keep when a variable is reused across registries and is EHR-derivable in coded form (demographics, diagnoses, the lab-value buckets, medications). For those, one governed source-to-OMOP-to-registry path beats N bespoke extractions and reduces burden. For genuinely registry-specific, adjudicated, non-coded variables, keep a direct-capture path and record it. The buckets and lab logic in the Hartfalen handboek are the sweet spot for the CDM route, which is why heart failure is the right first use case. The mapping from OMOP Measurement to NHR codes is itself a tabular mapping table, so it belongs in the same SSSOM-style artifact as every other terminology mapping, and its home is sssom-rosetta.

FHIR Provenance. To answer "how do we record that a measurement was determined as part of a quality registration, giving it higher reliability", Provenance is the right FHIR resource: it records the activity, the source entities and the responsible agents behind a resource, for assessing reliability and trust. Practically, prefer native fields first (Observation.performer, .device, .method, meta.source) and mint a Provenance where extra lineage or an explicit reliability assertion is required. Note the split: FHIR Provenance covers record lineage, SSSOM covers concept-mapping lineage, and OMOP's `*_source_concept_id` and `*_source_value` cover only a fraction. We likely need all three, and they should agree.

## 5. Reuse, contribute, build

The through-line across every external is that what is worth reusing is their standards and interfaces, not their runtime code. That is what lets sssom-rosetta become the convergence point, a full mapping suite, without inheriting anyone's pandas or Postgres. The suite has two halves: authoring and validation, which is what sssom-rosetta already is, and discovery, the candidate generation Ariadne does, which is the half we add by rebuilding its logic in Polars and DuckDB rather than adopting its code. Whether discovery ships as a component beside sssom-rosetta or inside it is left open in section 3.5, but either way the value reused is the algorithm, not the package. The externals fall into two kinds: SSSOM, SQL-on-FHIR and the Vulcan IG are standards we adopt, while fhir2omop and Ariadne are producers and references we interoperate with and reuse the logic from, not runtimes we depend on.

| External | Reuse (standard or logic, not code) | Contribute back | Role in the suite |
| --- | --- | --- | --- |
| SSSOM / Mapping Commons | The interchange format: predicates, provenance columns, schema | Publish our OMOP and NHR mapping sets, and a Dutch-healthcare set | The spine and on-disk contract |
| SQL-on-FHIR ViewDefinition | The flatten spec, portable FHIRPath projections | A DuckDB or Polars runner, or test cases, since no Polars-native engine exists | Layer-1 field-map format |
| HL7 Vulcan FHIR-to-OMOP IG | Field edges and ConceptMaps as upstream truth | Implementer feedback and gap reports | Source of the field maps |
| fhir2omop | GAPS.md logic, the Observation-to-Measurement routing, its 26 ViewDefinitions (Apache-2.0 JSON) | Align to its mapspec, and feed a DuckDB port back | Reference and starter content |
| Ariadne / Usagi | The discovery logic (normalization, verbatim match, vector search, hierarchy selection), rebuilt in Polars and DuckDB; the `AbstractConceptSearcher` interface; the candidate-plus-curate workflow | A DuckDB searcher that drops Postgres, offered back to Ariadne | The discovery half of the suite, producing candidate SSSOM rows |

The mechanism that makes it a suite is a thin adapter per producer, each normalizing a native output into the one SSSOM contract: a Usagi export becomes SSSOM, an Ariadne flat table becomes SSSOM, fhir2omop's ConceptMaps become SSSOM, and OMOP's own `concept_relationship` "Maps to" rows become SSSOM. Once everything lands in that contract, the content-agnostic engine (section 3.3) validates and transforms it uniformly. So "use the same logic and standards" is concrete: it is a set of importers to a shared schema, not a dependency on external code.

What stays ours to build, because none of the externals provide it, is the run-time application in pluginlake (the ViewDefinition runner, the concept joins, the gold registry logic and the missing Measurement table), the nyctea validation wiring, and the NHR Hartfalen logic itself.

The community line follows from this. Interoperate at the standard boundary, contribute narrow high-value backends (the DuckDB searcher for Ariadne is the flagship), and publish our mapping sets as SSSOM. That keeps the OHDSI, HL7 and SSSOM communities on board, because they can consume what we produce, and it avoids the two failure modes of forking their tools or reimplementing them.

## 6. End-to-end pipeline and where each piece plugs in

The three-layer transform (section 2), the design-time vs run-time split, and pluginlake's medallion combine into one pipeline.
Reading it top to bottom shows every step; the overlap map below shows where tools could do the same job, and how we keep them from colliding.

Design-time (authoring, central, occasional, produces versioned artifacts):

| Step | What happens | Primary tool or technique | Status |
| ---- | ------------ | ------------------------- | ------ |
| D1 | Author structural field maps (FHIR field to OMOP column) | SQL-on-FHIR ViewDefinitions; fhir2omop and the HL7 Vulcan IG as reference | to decide |
| D2 | Generate concept-map candidates, then curate to OMOP `concept_id` | discovery (Ariadne logic rebuilt in Polars and DuckDB: normalization, verbatim, DuckDB vector search) produces candidates; sssom-rosetta authors and validates the curated SSSOM table | partial |
| D3 | Author registry maps and logic (OMOP concept to NHR code, Hartfalen buckets) | sssom-rosetta plus a registry spec | gap |
| D4 | Author validation schemas (parsers and checks) | nyctea schema (YAML, JSON or dict) | to add |

Run-time (pluginlake, per hospital, federated, applies the artifacts across the medallion):

| Step | What happens | Primary tool or technique | Status |
| ---- | ------------ | ------------------------- | ------ |
| R0 | Ingest EPD extract as FHIR R4 NDJSON (and OMOP CSV) into landing | Dagster ingestion assets | exists |
| R1 | Load raw to bronze | Dagster plus the DuckLake IO manager | exists |
| R2 | Validate FHIR before mapping | nyctea asset check | to add |
| R3 | Structural flatten, layer 1 (project, unnest, cast, pick a coding) | ViewDefinition via a DuckDB SoF engine | to build |
| R4 | Concept resolution, layer 2 (code to `concept_id`) | DuckDB or Polars join on sssom-rosetta maps | to build |
| R5 | OMOP shaping, layer 3 (Measurement routing, fan-out or pick-one, keys, eras) | Polars or DuckDB SQL in gold | partial (Measurement gap) |
| R6 | Validate OMOP and vocabulary referential integrity | nyctea checks, replacing hand-rolled checks and rosetta's RI check | to add |
| R7 | Registry gold: apply Hartfalen logic (OMOP to NHR codes) | Polars or DuckDB SQL driven by the D3 maps | gap (biggest) |
| R8 | Validate registry output and capture Provenance | nyctea plus FHIR or OMOP provenance | gap |
| R9 | Serve to consumers | FastAPI gateway and Streamlit datastation | exists |

### Overlap map

Where more than one tool could do a job, this is the overlap and the rule that resolves it.

| Concern | Tools that overlap | How we resolve it |
| ------- | ------------------ | ----------------- |
| Transformation | ViewDefinition (R3) vs DuckDB or Polars SQL (R5, R7) vs nyctea parsers | ViewDefinition owns the FHIR-shaped structural flatten only; computed and OMOP logic is Polars or SQL; nyctea parsers stay lightweight coercions beside validation, not a transform engine |
| Validation | nyctea vs hand-rolled `omop/validation.py` vs sssom-rosetta's referential-integrity check | nyctea is the one engine, Dagster asset checks are the harness that runs it; retire the hand-rolled checks; move rosetta's RI check to a nyctea or DuckLake check |
| Concept-map production | Ariadne (logic rebuilt in Polars and DuckDB) vs Usagi vs hand curation | interchangeable producers of one SSSOM table; the shared tabular contract (section 3.5) is the only interface |
| Vector / nearest-neighbour search | Postgres pgvector (Ariadne) vs DuckDB exact cosine vs DuckDB VSS vs numpy vs Polars | drop Postgres; default to DuckDB exact `array_cosine_distance` over a filtered candidate set (numpy for the in-Python path); use DuckDB VSS only if scale demands; not Polars, which has no ANN; no separate vector database |
| Mapping representation | SSSOM (concept to concept) vs ViewDefinition (field to column) vs FML | not a real overlap; these are different layers (section 2), and SSSOM never expresses a transform |
| Compute engine | DuckDB vs Polars | both run over the same DuckLake Parquet; DuckDB for SoF and heavy joins, Polars for dataframe transforms and nyctea; not a conflict |
| Catalog and lineage | Dagster asset graph vs DuckLake catalog vs nyctea's future scope | Dagster owns lineage and orchestration, DuckLake owns the table catalog; nyctea composes with both (see note) |

Note on nyctea's direction. The aim is for nyctea to grow into a dbt-for-dataframes layer with lineage, catalog, testing, validation and transformation. Today it is a validation library, and that is how this analysis scopes it. Two of those future concerns already have owners here: Dagster provides orchestration and asset lineage, and DuckLake provides the table catalog. So nyctea's durable, non-overlapping niche is the declarative validate-plus-transform DSL over Polars (its parsers and checks), composing with Dagster and DuckLake rather than reimplementing their lineage and catalog. Worth keeping in view when nyctea's scope is set, so the three do not collide.

### Concrete seams

The seams that make the roadmap actionable.

- Structural flatten (to build): run SQL-on-FHIR ViewDefinitions with a DuckDB SoF engine to flatten FHIR NDJSON into wide tables in DuckLake, at bronze-to-silver. The current `fhir/translator_registry.py` seam is limited and does not cover lab-value Observations; replace or drive it from this step, and encode the Observation-to-Measurement routing here.
- Validation (to add): introduce nyctea as a Dagster resource and express validation as asset checks at three points: pre-mapping FHIR profile validation between bronze and silver, post-mapping OMOP validation before the omop assets, and vocabulary resolution at gold. Retire the hand-rolled `omop/validation.py` and `omop/vocabulary_validation.py` behind nyctea.
- Terminology and registry mapping tables (to add): sssom-rosetta is the authoring home for the SSSOM-style tables (source code to OMOP concept, and OMOP Measurement to NHR code); pluginlake applies them in gold as DuckDB or Polars joins. Authored centrally (by hand curation or Ariadne as a candidate producer), never recomputed at run time.
- Registry gold layer (to build): the missing gold, registry-specific asset where NHR Hartfalen logic (the handboek buckets and derivations) is applied. This is the single biggest build gap and the heart of the use case.

## 7. Scenarios

Three shapes are worth comparing head to head. The first uses every package as it is today, the second builds one in-house suite by maturing sssom-rosetta and rebuilding Ariadne's logic in our stack, and the third is a pragmatic hybrid that mixes the two by timescale. Each is judged on the same axes: upsides, downsides, maintainability, security and consequences. The holes that any full pipeline must still fill, and the assets pluginlake needs, are shared across all three and listed after.

### 7.1 Scenario A: use every package as-is

Run the tools unchanged. Ariadne runs centrally on pandas with Postgres and pgvector for discovery, sssom-rosetta runs as-is (content-in-code, maplib and rdflib, a single mapping set, no CI or LICENSE) for authoring and validation, fhir2omop's ViewDefinitions and Stage-2 SQL run on Bun over Postgres for the FHIR flatten, and nyctea validates. pluginlake orchestrates and applies the finished mapping tables.

Upsides. Fastest route to a first end-to-end demo, because nothing is rebuilt and each tool already works in its own domain. Ariadne's vector search and optional LLM are available immediately for hard discovery, fhir2omop's 26 ViewDefinitions and GAPS.md are usable directly, and staying on the original code keeps the external maintainers' work intact and the fork risk low.

Downsides. A heavy, polyglot stack: Python with pandas, TypeScript on Bun, two Postgres instances, pgvector, spacy, maplib and rdflib, alongside our own Polars and DuckDB. Two mapping representations coexist (fhir2omop ConceptMaps and SSSOM) and must be reconciled. sssom-rosetta as-is means every new vocabulary or mapping set is a code change in three or four places. Version and dependency conflicts are likely (Python 3.12 versus 3.13, pandas versus Polars, forked alpha dependencies), and the missing LICENSE on sssom-rosetta is a real blocker to depending on or distributing it.

Maintainability. Low. Single maintainers and alpha status on every external mean we do not control the release cycles, so upstream fixes land on their schedule and our pipeline is pinned to moving alphas. Operating two languages doubles the toolchain, CI and expertise the team must carry.

Security. The largest attack surface of the three: two database servers, pgvector, a Bun runtime, spacy models, and, if the cloud LLM is enabled, egress of source terms to a third party (not patient data, but local code descriptions can still be sensitive). More third-party alpha code sits in the trusted path, which is supply-chain risk, and the AGPL-3.0 licence of fhir4ds is a concern if it is the SoF engine.

Consequences. Quick to demo, slow and costly to harden, and you inherit everyone else's immaturity. The likely trajectory is that you rewrite the moving parts anyway, so the saved effort is borrowed, not free.

### 7.2 Scenario B: one suite, sssom-rosetta plus a rebuilt Ariadne

Build a single Python mapping suite on our stack. Mature sssom-rosetta into the content-agnostic authoring and validation engine, and add the discovery half by rebuilding Ariadne's logic (normalization, verbatim match, vector search, hierarchy selection, evaluation) in Polars, numpy and DuckDB. Drop pandas, Postgres, pgvector and Bun. pluginlake applies the resulting SSSOM tables, and nyctea validates.

Upsides. One language and one compute stack (Polars, numpy, DuckDB over DuckLake), which is coherent to build, secure and operate. No Postgres, no pgvector, no Bun, and no LLM by default, so the attack surface is minimal and there is no egress. The content-agnostic engine turns adding a mapping or vocabulary into data plus review rather than code, which is the onboarding process the opdracht wants. Because the suite is ours, production readiness (CI, LICENSE, tests) is actually reachable, and there is one SSSOM contract rather than two representations.

Downsides. Real upfront build cost for a small team: rebuild discovery, refactor sssom-rosetta, build the pluginlake apply and flatten assets. Reimplementation risk, because we may reproduce bugs Ariadne already fixed or miss its drug and procedure workflows, and we stop getting its upstream improvements for free. We now own the embedding-model choice and the gold-standard evaluation set needed to trust our own discovery. There is a political edge, since a full rebuild can read as a silent fork, which the searcher contribution only partly offsets.

Maintainability. High in the long run because it is one stack we control, but it depends on sustained capacity. nyctea and sssom-rosetta each have a single maintainer today, so the binding constraint is people, not design.

Security. The best posture of the three: no external services, no egress, deterministic and auditable, everything in DuckLake and Parquet, the LLM optional and off, embeddings local. The supply chain shrinks to Python, DuckDB, Polars and one embedding library.

Consequences. Slower to the first demo, faster and safer to production, and the shape that actually fits federated hospital deployment. It is the direct expression of the ownership framing in section 2: the mature core is ours.

### 7.3 Scenario C: pragmatic hybrid (leaning recommendation)

Split by timescale rather than by tool. Consume fhir2omop's ViewDefinitions and GAPS.md as pinned Apache-2.0 artifacts from day one, because they are JSON and documentation with no runtime to adopt. Use Ariadne as-is, once, centrally, to bootstrap the first Hartfalen mapping set, treating that run as throwaway scaffolding whose only output is a curated SSSOM table. Build for keeps only what sits on the recurring or federated path: the pluginlake run-time assets, nyctea validation, and the sssom-rosetta maturation. Rebuild Ariadne's discovery in our stack only once a second mapping set proves the need. This is also the shape that aligns with the OHDSI maintainer's work rather than competing with it: his tool authors the mappings centrally, we consume the SSSOM output, and the DuckDB searcher we build for the federated path is contributed back to Ariadne, so aligning with upstream and owning the federated stack are not in tension. If the maintainer is open to it, this hybrid extends naturally into co-evolving Ariadne toward the shared stack together rather than us rebuilding alone, which is worth putting on the table explicitly.

Upsides. Gets a vertical working quickly without putting any alpha external on the recurring path, defers the largest build (discovery) until it is justified, and keeps every long-lived component ours. Nothing a hospital runs depends on pandas, Postgres or Bun.

Downsides. Requires the discipline to treat the Ariadne bootstrap as disposable and not let it ossify into a dependency. Two ways of producing mappings exist during the transition (a one-off Ariadne run, then the rebuilt discovery), which must be kept clearly separated so the throwaway path is not quietly promoted.

Maintainability and security. Same end-state as Scenario B, reached incrementally, so the transitional risk is only that the central bootstrap environment (Postgres, an optional LLM) exists briefly and must be torn down, not shipped to hospitals.

Consequences. Proves the Hartfalen value first and pays down the platform debt second, which answers the direct-extraction critic on their own terms while still moving toward the owned, tabular, federated target.

### 7.4 Holes to fill for a full pipeline (shared across scenarios)

Independent of the scenario, the same gaps stand between us and one working EPD-to-registry flow:

- No ViewDefinition runner exists. Running SQL-on-FHIR needs a FHIRPath evaluator plus a DuckDB SoF engine (fhir4ds, note AGPL-3.0; FlatQuack; or a small in-house compiler). This is the biggest technical unknown.
- The OMOP Measurement table is not built, and the Observation-to-Measurement domain routing has no home. Heart failure is a lab-value story, so this is on the critical path.
- The concept-resolution join (layer 2, source code to `concept_id`) has no asset.
- The gold registry asset that applies the NHR Hartfalen buckets and derivations does not exist. This is the single biggest gap and the heart of the use case.
- The mapping tables themselves are unauthored (source-to-concept and OMOP-to-NHR), and the Handboek Hartfalen variable list has not yet been retrieved.
- The OMOP vocabulary tables (`CONCEPT`, `CONCEPT_ANCESTOR`, `CONCEPT_RELATIONSHIP`, `CONCEPT_SYNONYM`) must be loaded into DuckLake, since resolution, hierarchy, search and the referential-integrity check all join against them.
- nyctea is not wired as Dagster asset checks anywhere yet.
- Provenance capture for registry-derived measurements is not built.
- For discovery specifically: an embedding model must be chosen and concept embeddings generated, and a gold-standard evaluation set is needed before any automated suggestion can be trusted.

### 7.5 Assets we need

Design-time, authored centrally and published as versioned artifacts (in the suite, not per hospital):

- `omop_vocabulary`: the OMOP vocabulary tables loaded into DuckLake, shared by resolution, hierarchy, search and referential integrity.
- `concept_embeddings`: embeddings over concept names and synonyms, for the discovery vector search (Scenario B or C rebuild).
- `mapping_candidates`: discovery output, ranked source-term-to-concept candidates for human curation.
- `curated_mapping_set`: the validated SSSOM tables (source-to-concept and OMOP-to-NHR), the artifact pluginlake consumes.

Run-time, in pluginlake's medallion, applied per hospital:

- `fhir_landing` and `fhir_bronze`: ingest and land FHIR R4 NDJSON (exists).
- `fhir_validated`: nyctea asset check on FHIR profiles before mapping (to add).
- `fhir_flattened`: silver wide tables via the ViewDefinition runner, layer 1 (to build).
- `omop_measurement` and the other OMOP domain tables, including the Observation-to-Measurement routing (partial; Measurement is the gap).
- `concept_resolved`: layer 2, join the flattened codes onto `curated_mapping_set` to attach `concept_id` (to build).
- `omop_validated`: nyctea checks plus the referential-integrity check, replacing the hand-rolled validation (to add).
- `registry_hartfalen_gold`: layer 3, apply the Handboek bucket and derivation logic to Measurements (to build, the biggest gap).
- `registry_validated` and `provenance`: validate the registry output and capture lineage (to build).
- `gateway` and `datastation`: the FastAPI and Streamlit serving layer (exists).

### 7.6 At a glance

| Axis | A: all as-is | B: one owned suite | C: pragmatic hybrid |
| ---- | ------------ | ------------------ | ------------------- |
| Time to first demo | fastest | slowest | fast |
| Time to production | slowest | fast | fast |
| Stack surface | polyglot, two Postgres, Bun | one Python stack, DuckLake | one stack, brief central bootstrap |
| Maintainability | low, alphas we do not control | high, if capacity holds | high, incremental |
| Security | largest surface, possible egress | smallest, no egress | smallest end-state |
| Ownership of core | external | ours | ours |
| Main risk | inheriting others' immaturity | build cost and team capacity | letting the throwaway bootstrap ossify |

## 8. Functional roadmap (broad, phased)

Phase 0, decide and record. Write the ADR this document feeds. Lock: tabular-first, SSSOM as the mapping-table format, the exact/broad/narrow predicate set, the design-time vs run-time split, the discovery approach (reuse Ariadne's logic rebuilt in Polars and DuckDB, LLM optional and off, no separate vector database), whether discovery lives beside sssom-rosetta or inside the suite, and the structural-flatten choice (which DuckDB SoF engine, and its licence). Before locking the discovery approach, have an explicit conversation with the Ariadne maintainer about co-maintenance and a shared stack, since the choice between aligning centrally on his tool, co-evolving Ariadne toward Polars and DuckDB together, and rebuilding in our own stack depends on his appetite for maintaining together and on our own capacity. Pick one concrete Hartfalen slice (one lab value, its buckets) as the vertical.

Phase 1, close the run-time gap for the vertical. In pluginlake, add the structural flatten via a DuckDB ViewDefinition runner and encode the Observation-to-Measurement routing (porting fhir2omop's domain-routing rule). Wire nyctea as asset checks and add the first gold registry asset that applies the Hartfalen bucket logic to a Measurement. End state: one lab value flows EPD to FHIR Observation to OMOP Measurement to an NHR code, validated at each step.

Phase 2, make mapping an onboarding process, not development. Adopt the SSSOM-style mapping-table contract. Build the discovery half by rebuilding Ariadne's logic in Polars and DuckDB rather than running its code: deterministic normalization and verbatim matching, a DuckDB cosine-distance vector search over a filtered candidate set (no Postgres, no separate vector database), and human curation, with LLM selection optional and off by default and gated by a gold-standard regression set. Decide in this phase whether discovery ships as a component beside sssom-rosetta or inside one suite. Refactor sssom-rosetta into a content-agnostic engine, separating config, schemas, vocabularies and mappings from the code (vocabularies declared as sources rather than a module each) and discovering mapping sets from the filesystem, with CI and a LICENSE, so adding a mapping or a vocabulary is editing data plus review, not writing code. Add FHIR Provenance capture for registry-derived measurements.

Phase 3, generalize and give back. Extend from one lab value to the full Hartfalen minimal set, then to a second registry to prove reuse across hospitals. Contribute the DuckDB Ariadne searcher back to OHDSI, and engage the OHDSI NL node and the HL7 Vulcan IG with what we learned. Revisit the deferred RDF exports only if a concrete semantic-web consumer appears.

## 9. Open questions for the ADR

1. Structural transform (layer 1): where the field-map specification is authored, the ViewDefinition column list itself (pull upstream, simplest) or a separate declarative field map (FML from the HL7 IG) that generates it; which DuckDB SoF engine runs it (fhir4ds, note AGPL-3.0; FlatQuack; or a small in-house ViewDefinition-to-DuckDB-SQL compiler); and how much of fhir2omop's Stage-2 shaping SQL we port versus re-express.
2. Ariadne, reuse shape, home, and co-maintenance: we adopt Ariadne's approach, its `AbstractConceptSearcher` interface, the predicates, the evaluation methodology and the SSSOM contract, so the ideas are not in question. What is open is whether we align centrally on his tool as-is, co-evolve Ariadne toward a shared Polars and DuckDB stack together, or rebuild the discovery in our own stack, and that choice depends on an explicit conversation with the maintainer about maintaining together and on our own capacity. The leaning answer is to align centrally now and not rebuild while there is only one mapping set. Sub-questions if we do build in our stack: whether discovery lives beside sssom-rosetta or inside one suite (disjoint dependency trees versus one codebase we control, with optional extras as a middle option), which engine runs the vector search (DuckDB exact cosine over a filtered candidate set by default, numpy for the in-Python path, DuckDB VSS only at scale, never Postgres and no separate vector database), and whether to enable the LLM stage at all behind a gold-standard gate.
3. Mapping-table home: sssom-rosetta is the intended home for both the source-to-OMOP-concept and OMOP-to-NHR tables; the open part is whether it is worth splitting the run-time-applied tables into a smaller, leaner package separate from sssom-rosetta's authoring machinery.
4. How much SSSOM: which columns and provenance fields are mandatory for us, and where the vocabulary referential-integrity check runs (keep it against maplib's ontology graph, which is the current default, or point it at pluginlake's DuckLake concept table for reuse).
5. Provenance depth: native FHIR fields only, or minted Provenance resources for registry-derived measurements, and how that is represented once in OMOP.
6. The direct-extraction boundary: an explicit rule for which registry variables go through the CDM and which are captured directly.

## 10. Sources

- Local repos: `/Users/vinkels/Code/plugin-healthcare/pluginlake`, `.../sssom-rosetta`, `/Users/vinkels/Code/nyctea`.
- Prior settled context: `.agents/memory/viscosuite-integration-discussion.md`.
- External: `lampadephoros/fhir2omop` (README, `mapspec/GAPS.md`, `mapspec/profiles/Observation__measurement.profile.json`, issue #31); `OHDSI/Ariadne` (README, `pyproject.toml`, `src/ariadne/evaluation/concept_selection_evaluator.py`, `src/ariadne/vector_search/abstract_concept_searcher.py`, `src/ariadne/vector_search/pgvector_concept_searcher.py`, `src/ariadne/vector_search/hecate_concept_searcher.py`); sssom-rosetta internals (`mapping/validate.py`, `ontology/catalog.py`, `vocabulary/merge.py`); HL7 `sql-on-fhir` v2 IG; `mapping-commons/sssom` and its OMOP tutorial and `sssom-py` toolkit; HL7 Vulcan FHIR-to-OMOP IG; `nhr.nl` (over-nhr, registratie, handboeken); FHIR R4 Provenance (hl7.org/fhir/R4/provenance.html); OHDSI Europe NL national node page.

Uncertainties to verify before the ADR: SQL-on-FHIR sponsoring workgroup (likely FHIR-I, unverified); exact SSSOM released spec label (schema line is 1.1.0a5); no verified Dutch FHIR-to-OMOP registry project found; NHR Handboek Hartfalen variable list not yet retrieved (page is client-side rendered).
