# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- ADR-007: Dataspace Protocol, authentication, and authorization architecture (EHDS/Health-RI compliant, VC-native ODRL).
- `docs/background/` section for design research (not in public nav):
  - `dsp-authorization.md`: DSP design specification with options analysis, UX workflows, RBAC entity model, and implementation reference.
  - `federated-infrastructure.md`: federated infrastructure comparison (Nuts, vantage6, Flower, FLARE, EU dataspaces).

### Changed

- ADR-006 rewritten: scoped to Nuts as organizational identity layer only (node-to-node trust boundary). Added Processing Hub terminology, governance rules, trust boundary definitions, and credential role enforcement.
- ADR-003: clarified rejected "landing zone" alternative with explicit rationale for direct FastAPI-to-Dagster triggering.
- Docs nav restructured in `zensical.toml`: ADR-006 and ADR-007 added to Decisions section.

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
