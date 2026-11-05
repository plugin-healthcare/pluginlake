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
- Container entrypoint (`deploy/docker/entrypoint.sh`) that installs `$PLUGINLAKE_PROJECTS` on startup; the dev Dagster container creates its metadata database automatically, so a fresh station comes up fully working.
- `docs/guides/deploying-a-station.md`: how projects are onboarded via the entry point and how to bring a station up with `pluginlake.toml` and the CLI.
- Station monitoring (ADR-010): the API records request count, latency and exception metrics with bounded labels and serves them on an internal metrics port (`PLUGINLAKE_METRICS_PORT`, default 9464); compose profile `monitoring` with Prometheus, postgres-exporter and cAdvisor in the dev and production compose; scrape config in `deploy/monitoring/prometheus/` with optional `remote_write` to central monitoring; `[monitoring]` section in `pluginlake.toml` picked up by `pluginlake up`; `docs/guides/monitoring.md`.
- `docs/background/` section for design research (not in public nav):
  - `dsp-authorization.md`: DSP design specification with options analysis, UX workflows, RBAC entity model, and implementation reference.
  - `federated-infrastructure.md`: federated infrastructure comparison (Nuts, vantage6, Flower, FLARE, EU dataspaces).

### Changed

- ADR-006 rewritten: scoped to Nuts as organizational identity layer only (node-to-node trust boundary). Added Processing Hub terminology, governance rules, trust boundary definitions, and credential role enforcement.
- ADR-003: clarified rejected "landing zone" alternative with explicit rationale for direct FastAPI-to-Dagster triggering.
- Docs nav restructured in `zensical.toml`: ADR-006, ADR-007, and ADR-008 added to Decisions section.
- License changed from MIT to Apache-2.0.
- Production `pluginlake` image copies `README.md`, which the project build requires.
- Production Dagster webserver/daemon image no longer installs pluginlake or its data dependencies (about 960 MB to 220 MB): it installs the new `dagster-webserver` dependency group and runs the standalone `dagster_env` launcher as a single file. `DagsterPostgresSettings` moved from `pluginlake.config` to `pluginlake.deploy.dagster_env`.
- Production compose rotates container logs (`json-file`, 5 × 10 MB per container); Docker kept them without limit before.
- Credentials are Docker Compose secrets in the dev and production compose: compose reads them from a compose-only env file (`deploy/compose/.env` in dev, the new `.env.production.secrets` in production) and mounts them under `/run/secrets/`. `DuckLakeSettings` and the new `DagsterPostgresSettings` read them with pydantic `secrets_dir`; postgres and postgres-exporter use `<VAR>_FILE`. `dagster.yaml` still needs `DAGSTER_PG_PASSWORD`, which the new `pluginlake.deploy.dagster_env` launcher sets for the Dagster processes only (and, with `--ensure-db`, replaces `$PLUGINLAKE_ENSURE_DB`). `DuckLakeSettings.pg_password` is now a `SecretStr`. Dev containers no longer load the root `.env` (optional `deploy/compose/.env.containers` instead); `.env.production` no longer holds passwords, `.env.postgres-exporter` is removed, and the remote-write password moved from `.env.monitoring` to the secrets env file. `just up`/`down` pass both production env files.
- Dependency audit: `just secure` and the security workflow use `uv audit` instead of the deprecated, archived `uv-secure` (the `security` dependency group is removed).
- Upgraded vulnerable dependencies: streamlit 1.66.1 (pillow 13.0.0; the `starlette` extra is gone, starlette is now built in), dnspython 2.9.2, filelock 4.2.9, graphql-core 3.2.13, setuptools 84.2.1, packaging 26.3, virtualenv 21.15.5; tornado is no longer installed.

### Removed

- Unused `PostgresSettings` (`PLUGINLAKE_POSTGRES_*`) and `DagsterSettings` (`PLUGINLAKE_DAGSTER_*`), which duplicated the DuckLake and Dagster connection settings; `DagsterPostgresSettings` (`DAGSTER_PG_*`, the variables `dagster.yaml` reads) replaces the latter. The generic `*_FILE` launcher and the `PLUGINLAKE_ENSURE_DB` entrypoint step are gone.
- Plugin architecture Phase 4: removed all in-tree domain code from core — the `omop/`, `fhir/`, and `assets/` packages, their Dagster definitions, OMOP/FHIR API routers and ingestion services, `utils/testdata.py`, related scripts, notebooks, and tests. This code now lives in the `pluginlake-ehds-demo` package. Core retains only the generic platform (DuckLake, storage, generic ingestion, the FastAPI gateway, and the plugin host).
- OMOP/FHIR reference docs moved out of core into the `pluginlake-ehds-demo` project (they document project-owned modules); core's reference nav and `docs/reference/{ingestion,index,utils}.md` updated accordingly. Removed the `fhir` and `synthea` optional-dependency extras.

### Fixed

- Production Dagster webserver and daemon crashed at start: Dagster telemetry wrote to `$DAGSTER_HOME/logs`, which the non-root user cannot write. Telemetry is now disabled in `config/dagster/dagster.yaml` (dev and production).
- Production `dagster-daemon` exited because it got no workspace; the compose command now passes `-w /app/config/dagster/workspace.yaml`.
- Production runs failed before starting: they execute in the code server, which lacked `dagster-postgres` and `DAGSTER_PG_PASSWORD`. `dagster-postgres` is now a core dependency (moved from the `infra` extra) and the code server gets the `dagster_pg_password` secret through the `dagster_env` launcher.
- Production compute log capture failed (no `tail` in the hardened images) and the webserver could not read the logs anyway. Production now uses `config/dagster/dagster.production.yaml` with `NoOpComputeLogManager`: `context.log` messages show in the UI, step stdout/stderr in the code-server container log. The unused `dagster-compute-logs` volume is removed.

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
