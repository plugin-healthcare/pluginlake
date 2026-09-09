# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- ADR-008: Dataspace Protocol, authentication, and authorization architecture (EHDS/Health-RI compliant, VC-native ODRL).
- ADR-009: Core platform and project plugin architecture (split platform from projects; entry-point plugins for code locations, routers, and UI; CLI + templates for project conformance).
- Plugin architecture Phase 1: `pluginlake.projects` entry-point discovery and a declarative `ProjectManifest`; core mounts project routers and Dagster code locations without importing project code. OMOP/FHIR registered in-tree via the `ehds-demo` manifest (non-breaking).
- Plugin architecture Phase 2: the `pluginlake` CLI (`init` scaffolds a conformant project package, `verify` runs the conformance suite), a project template, shared base classes (`ProjectSettings`, framework-agnostic `Connector`, catalog/namespace helpers), and the conformance suite (manifest validation, core-version compatibility, catalog/namespace uniqueness, import and settings checks).
- Plugin architecture Phase 3: extracted the OMOP/FHIR demo into the standalone `pluginlake-ehds-demo` package, which plugs into core through the `pluginlake.projects` entry point and reproduces the former in-tree behaviour.
- Config-driven station deploy: `pluginlake.toml` station config (Pydantic-validated) declaring node settings and the projects to deploy (local `path` for dev or pinned `source` for prod), and `pluginlake up`/`down` CLI commands that build and run the stack, install the configured projects into the standardized images at container start, and let discovery wire their code locations and routers — no files copied by hand.
- Container entrypoint (`deploy/docker/entrypoint.sh`) that installs `$PLUGINLAKE_PROJECTS` and provisions required databases (`$PLUGINLAKE_ENSURE_DB`) on startup, so a fresh station comes up fully working (Dagster's metadata database is created automatically).
- `docs/guides/deploying-a-station.md`: how projects are onboarded via the entry point and how to bring a station up with `pluginlake.toml` and the CLI.
- `docs/background/` section for design research (not in public nav):
  - `dsp-authorization.md`: DSP design specification with options analysis, UX workflows, RBAC entity model, and implementation reference.
  - `federated-infrastructure.md`: federated infrastructure comparison (Nuts, vantage6, Flower, FLARE, EU dataspaces).

### Changed

- ADR-006 rewritten: scoped to Nuts as organizational identity layer only (node-to-node trust boundary). Added Processing Hub terminology, governance rules, trust boundary definitions, and credential role enforcement.
- ADR-003: clarified rejected "landing zone" alternative with explicit rationale for direct FastAPI-to-Dagster triggering.
- Docs nav restructured in `zensical.toml`: ADR-006, ADR-007, and ADR-008 added to Decisions section.
- License changed from MIT to Apache-2.0.

### Removed

- Plugin architecture Phase 4: removed all in-tree domain code from core — the `omop/`, `fhir/`, and `assets/` packages, their Dagster definitions, OMOP/FHIR API routers and ingestion services, `utils/testdata.py`, related scripts, notebooks, and tests. This code now lives in the `pluginlake-ehds-demo` package. Core retains only the generic platform (DuckLake, storage, generic ingestion, the FastAPI gateway, and the plugin host).
- OMOP/FHIR reference docs moved out of core into the `pluginlake-ehds-demo` project (they document project-owned modules); core's reference nav and `docs/reference/{ingestion,index,utils}.md` updated accordingly. Removed the `fhir` and `synthea` optional-dependency extras.

## [0.1.1] — 2026-06-03

### Security

- Tornado bumped 6.5.4 → 6.5.5 (dependabot).

## [0.1.0] — 2026-03-16

### Highlights

- DuckLake-backed data catalog with PostgreSQL catalog metadata.
- Dagster orchestration with custom DuckLake I/O manager.
- FHIR ingestion into OMOP CDM.
- FastAPI data access layer.
- Datastation dashboard (Streamlit).
- Docker Compose setup for dev and prod.
- Azure infrastructure (OpenTofu modules).
- Documentation site via GitHub Pages.
- CI/CD with GitHub Actions.
- OMOP vocabulary support.
