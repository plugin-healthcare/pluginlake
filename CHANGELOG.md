# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Production-ready Docker Compose setup with separate webserver, daemon, and code-server containers matching Dagster's recommended architecture.
- `pluginlake` CLI module (`src/pluginlake/cli/`) with `init`, `up`, `down`, `status`, `list` subcommands for deployment management.
- XDG-compliant path layout (`~/.config/pluginlake/`, `~/.local/share/pluginlake/`, `~/.local/state/pluginlake/`) for host-side configs, data, and logs.
- Deploy templates (`deploy/templates/`) for `.env`, `dagster.yaml`, and `workspace.yaml` generation.
- Smoke test compose file (`docker-compose.smoke.yaml`) for CI/CD integration testing.
- Deployment guide (`docs/guides/deployment.md`) covering both CLI and manual Docker workflows.
- Docker security hardening: required-variable syntax (`${VAR:?must be set}`), path traversal validation on `instance_id`, `PUID`/`PGID` convention for user mapping.

### Changed

- Unified environment config: single `.env` + `.env.example` (removed separate `.env.production.example`).
- Renamed `dagster-webserver.Dockerfile` to `dagster.Dockerfile`.
- Dev compose (`docker-compose.dev.yaml`) now mirrors prod architecture (5 containers) with source mounts for hot reload.
- `justfile` cleaned up: `up` uses `--env-file` explicitly, added `up-ui` recipe, `smoke-test-full` includes `--build`.
- README updated with real dev architecture (5 containers) and smoke test section.
- Switched from `UID`/`GID` to `PUID`/`PGID` env vars (bash `UID` is readonly).

### Fixed

- Port mismatch between Dockerfile hardcoded `--port 8000` and `.env` setting `PLUGINLAKE_SERVER_PORT=8001` causing health check failures.
- OOM kills from concurrent dagster jobs: removed hardcoded `mem_limit: 4g` / `cpus: 2.0` resource limits.
- Type errors in CLI settings (`SecretStr` default handling) and init module.

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
