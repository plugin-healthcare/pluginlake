# Handover: mapping/validation stack analysis

Date: 2026-08-26
Author: @yannick-vinkesteijn (with Copilot)

## What this session did

Extended `.agents/plan/202608261400_mapping-validation-stack-analysis.md` (the deliverable feeding a future ADR). Focus was the Ariadne and sssom-rosetta positioning, plus an architect-alignment situation.

## Decisions landed

- Compute stack: Polars/Python (numpy allowed) and DuckDB only. No LanceDB, no separate vector database. Vector search is DuckDB exact `array_cosine_distance` over a filtered candidate set by default, DuckDB VSS only at scale.
- Design-time vs run-time split holds. sssom-rosetta authors and validates; pluginlake applies mappings as Polars/DuckDB joins. Ariadne's Postgres is only a swappable vector index, not core.
- Ariadne: adopt the approach, interface (`AbstractConceptSearcher`), predicates, eval methodology and SSSOM contract. Objection is deployment-fit and maturity, not the ideas. LLM stays optional and off by default.
- Ownership framing: we control pluginlake, nyctea, sssom-rosetta (maturity risk removable); externals are data/standards dependencies, not code. Mature core that runs federated is only pluginlake + nyctea.

## Document now contains

- §2 ownership split (maturity vs deployment-role).
- §3.3 sssom-rosetta: OMOP-aware validation as the differentiator vs `sssom-py`; RI check is an rdflib set-membership test portable to a DuckDB semi-join; "transform" = artifact generation, not data ETL.
- §3.4 fhir2omop (lampadephoros): reference and content source, not a runtime. Reuse the spec (field edges, profiles, 26 ViewDefinitions, `GAPS.md`) and its Observation-to-Measurement routing idea; do not port the TypeScript/Postgres runtime. DuckDB is the target if we ever run its ViewDefinitions.
- §3.5 Ariadne: authoring-vs-discovery framing; reuse logic, rebuild in Polars/DuckDB; Postgres = vector index only; deployment-fit-not-quality framing.- §3.6 Candid engineering assessment (internal): honest critique of code/tool/stack per repo, kept separate from the constructive maintainer-facing register.
- §5 Reuse/contribute/build; §6 pipeline tables + overlap map; §7 three scenarios (A all-as-is, B one owned suite, C pragmatic hybrid = leaning recommendation) with holes-to-fill and the asset list; §8 roadmap; §9 open questions; §10 sources.

## Architect situation (open, sensitive)

Architect built sssom-rosetta and knows the Ariadne maintainer (prominent OHDSI maintainer) well; prefers to align, not rebuild from scratch. A Dutch draft reply was written (in chat, not sent) that: leads with agreement, corrects "from scratch", scopes the only hard divergence to the federated runtime stack, proposes running his tool centrally + contributing a DuckDB searcher back, and asks to discuss co-maintenance together. Doc Phase 0 and open question 2 now flag the co-maintenance conversation as a decision input; co-evolving Ariadne together is a named fourth option between adopt and rebuild.

## Next steps (tomorrow)

- Decide whether to send/adjust the Dutch reply to the architect; set up the three-way conversation about co-maintenance.
- Confirm whether the doc should lead with the hybrid (C) as the recommendation or keep B and C as peers.
- Still owed from earlier: the fuller critical evaluation of open pipeline risks (FHIR profile assumptions for Dutch EPD/Nictiz/zib exports; predicate run-time semantics for broad/narrowMatch; where Observation-to-Measurement routing lives given it needs concept domain; SoF engine/licence choice).
- Retrieve the Handboek Hartfalen variable list (page is client-side rendered) to author the first mapping set.

## Constraints

- Never commit; the developer commits.
- Markdown: no hard-wrap, full sentences, minimal bold, no em dashes.
