# Docker guide

This guide covers how pluginlake uses Docker for development and production, including image strategy, multi-stage builds, and secrets management.

## Container architecture

pluginlake uses separate containers for each concern:

| Container | Dockerfile | Purpose |
|-----------|-----------|---------|
| **postgres** | `dhi.io/postgres:17-alpine3.24` (pre-built) | Dagster metadata + DuckLake catalog |
| **dagster-webserver** | `dagster-webserver.Dockerfile` (image `dagster-webserver`) | Dagster web UI |
| **dagster-daemon** | `dagster-webserver.Dockerfile` (image `dagster-webserver`) | Schedules, sensors, run queue |
| **dagster-code-server** | `api.Dockerfile` (image `api`) | Asset definitions served via gRPC |
| **pluginlake** | `api.Dockerfile` (image `api`) | FastAPI service |
| **dashboard-datastation** | `ui.Dockerfile` (`APP=datastation`, image `ui-datastation`) | Datastation Streamlit dashboard (profile `ui`) |
| **pluginlake-central** | `ui.Dockerfile` (`APP=central`, image `ui-central`) | Central aggregation dashboard |
| **prometheus** | `quay.io/prometheus/prometheus` (pre-built) | Metrics store, profile `monitoring` |
| **postgres-exporter** | `quay.io/prometheuscommunity/postgres-exporter` (pre-built) | Postgres metrics, profile `monitoring` |
| **cadvisor** | `ghcr.io/google/cadvisor` (pre-built) | Container metrics, profile `monitoring` |
| **marquez-db** | `dhi.io/postgres:17-alpine3.24` (pre-built) | Marquez database (profile `lineage`) |
| **marquez** | `marquezproject/marquez:0.51.1` (pre-built) | OpenLineage receiver API (profile `lineage`) |
| **marquez-web** | `marquezproject/marquez-web:0.51.1` (pre-built) | Lineage web UI, host loopback only (profile `lineage`) |

Every image in the compose files is pinned by digest (`name:tag@sha256:...`), and so is every base image in the Dockerfiles; Dependabot proposes updates for both.
Our own four images are released to `ghcr.io/plugin-healthcare/pluginlake/<image>` by the release workflow, see [security](security.md).

The monitoring services only start with `--profile monitoring` (or `[monitoring] enabled = true` with `pluginlake up`); see the [monitoring guide](monitoring.md).

In development, `dagster.dev.Dockerfile` replaces the webserver, daemon, and code-server with a single all-in-one container running `dagster dev`. The UI containers use `ui.dev.Dockerfile` with hot reload. Both dashboards share one Dockerfile; the build arguments `APP` (`datastation` or `central`) and `PORT` (8501 or 8502) select the dashboard.

## Building and running

### Development

```bash
just dev-up        # Build and start all dev containers
just dev-down      # Stop and remove dev containers
```

This uses `deploy/compose/docker-compose.dev.yaml`. Source code is volume-mounted into the containers, so changes are picked up immediately without rebuilding.

### Production

Stations run the production stack with the released images through `pluginlake up`, without a checkout; see [deploying a station](deploying-a-station.md).
The stack is part of the package: `src/pluginlake/deploy/stack/docker-compose.yaml`, with the Prometheus and Marquez configuration next to it.
It has no `build:` sections; our images are set through `PLUGINLAKE_IMAGE_*` variables from the images lock.

To test the production stack with images built from a checkout:

```bash
just up            # Build the images and start the production stack
just down          # Stop and remove the production containers
```

This adds `deploy/compose/docker-compose.build.yaml` (the `build:` sections) and uses `deploy/compose/` as compose project directory, so it reads `deploy/compose/.env.production` and `deploy/compose/secrets/`.

### Building individual images

```bash
just images        # api, dagster-webserver, ui-datastation and ui-central, tagged pluginlake/<image>:local
```

The build context is always the project root because the Dockerfiles need access to `pyproject.toml`, `uv.lock`, `src/`, and `config/`.
The `Images` workflow builds the same four images on every pull request and push to main.

## Projects and database provisioning

The development images (`pluginlake.dev.Dockerfile` and `dagster.dev.Dockerfile`) share the entrypoint `deploy/docker/entrypoint.sh`.
It runs before the service starts and reads `PLUGINLAKE_PROJECTS`: whitespace-separated `uv pip install` arguments for the project packages to install.
The production images do not run this entrypoint, so the variable has no effect there: the production stack does not install projects yet.

Projects register themselves through the `pluginlake.projects` entry point, so the core discovers their code locations and routers without importing project code (ADR-009).
In development, point `PLUGINLAKE_PROJECTS` at a local editable checkout:

```bash
PLUGINLAKE_PROJECTS="-e /opt/projects/my-project"
```

As an alternative to an editable checkout, use a pinned spec:

```bash
PLUGINLAKE_PROJECTS="my-project@git+https://github.com/org/my-project@v1.2.3"
```

Projects are installed with `--no-sources`, so the `[tool.uv.sources]` table of a project is ignored inside the image.
The dev Dagster container creates its own database on start when it does not exist yet (`dagster_env --ensure-db`, see [secrets](#secrets)); DuckLake creates its catalog database the same way.
The databases are currently created with the Postgres superuser; per-component roles are tracked in #224.

## Smoke test

The smoke test checks the core stack only, without any project installed.
It verifies that the API and Dagster answer, that the core API routers respond, that every Dagster code location loads, and that a generic file upload through `POST /api/v1/ingest` is stored.
Project pipelines are tested in their own repositories.

```bash
just smoke-test        # Run against an already running stack
just smoke-test-full   # Start an isolated stack, run the test, tear it down (removes volumes)
```

`smoke-test-full` reads `deploy/compose/smoke.env` and `deploy/compose/smoke.secrets.env`, so it does not depend on your local `.env`.
`smoke.env` holds non-secret settings: it is passed to compose with `--env-file` for interpolation and loaded into the containers through `PLUGINLAKE_ENV_FILE=smoke.env`.
`smoke.secrets.env` holds the throwaway passwords and is only passed with `--env-file`, like `deploy/compose/.env` in normal dev.
`PLUGINLAKE_ENV_FILE` (default `deploy/compose/.env.containers`, optional) is the only env file the dev containers load; never put passwords in it.

It publishes the same host ports as the dev stack, so stop `just dev-up` first if a port is already in use.

## Hardened base images

All Dockerfiles use hardened images from `dhi.io/` instead of the default Docker Hub images, pinned by digest:

```dockerfile
FROM dhi.io/python:3.13-debian13-dev@sha256:... AS builder    # Build stage
FROM dhi.io/python:3.13-debian13@sha256:...                    # Runtime stage
```

Postgres (`dhi.io/postgres:17-alpine3.24@sha256:...`) is pinned the same way in the compose files.

**Why hardened images?**

Standard images from Docker Hub (e.g. `python:3.13-slim`) ship with the full upstream package set and default configurations. Hardened images are rebuilt with security fixes applied, unnecessary packages removed, and restrictive defaults set. This reduces the attack surface and helps meet compliance requirements in healthcare environments.

**Prerequisites:**

Hardened images are distributed through Docker Hub and require authentication to pull, also on a station (the Postgres image). Before building any of the project's Docker images:

1. Create an account at [hub.docker.com](https://hub.docker.com) if you don't have one.
2. Log in from the CLI:

   ```bash
   docker login dhi.io
   ```

3. Browse the available hardened images at the [Docker Hub Hardened Images Catalog](https://hub.docker.com/hardened-images/catalog). Note that not all images are free — some require a Docker Pro, Team, or Business subscription.

**What `dhi.io/` provides:**

- Vulnerability patching on a regular cadence
- Stripped-down package set (no compilers, shells, or debug tools in runtime images)
- Non-root default user where possible
- SBOM (Software Bill of Materials) for auditability

**Dev vs runtime variants:**

- `dhi.io/python:3.13-debian13-dev` — includes build tools (gcc, headers) needed to compile Python packages with C extensions. Used only in the build stage.
- `dhi.io/python:3.13-debian13` — minimal runtime. No compilers, no pip, no development headers.

The `uv` binary is similarly pulled from a hardened image rather than installed via curl:

```dockerfile
COPY --from=dhi.io/uv:0-debian13-dev@sha256:... /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/
```

## Multi-stage builds

Production Dockerfiles use multi-stage builds to keep final images small and secure.

### How it works

**Stage 1 — Build:** Install dependencies and compile the project using the dev image (which has compilers and build tools):

```dockerfile
FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev --no-editable
```

The build stage also compiles the bytecode and installs the DuckDB extensions (`ducklake`, `postgres`), because the runtime cannot write files or download extensions.

**Stage 2 — Runtime:** Copy only the virtual environment into the minimal runtime image and switch to the non-root user:

```dockerfile
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/.duckdb /app/.duckdb

ENV PATH="/app/.venv/bin:$PATH" HOME=/app
USER 65532:65532
```

### Why this matters

- **Smaller images:** The runtime image doesn't contain compilers, headers, pip, or uv — only what's needed to run.
- **Fewer vulnerabilities:** Build tools are the most common source of CVEs. They never make it into the final image.
- **Faster deploys:** Smaller images push and pull faster.

### Dev images skip multi-stage

Dev Dockerfiles use a single stage because they need the full toolchain for hot reload, debugging, and `dagster dev`:

```dockerfile
FROM dhi.io/python:3.13-debian13-dev
# ... install everything in one stage
CMD dagster dev -h 0.0.0.0 -p 3000 -m "$DAGSTER_MODULE"
```

## Environment variables and secrets

### The problem

Containers need configuration (database host, ports) and secrets (passwords, API keys). These should not be hardcoded in Dockerfiles or compose files, and secrets must never be committed to version control.

Configuration is passed as environment variables. Passwords are Docker Compose secrets, mounted as files under `/run/secrets/`.
They are not part of any container's configuration (`docker inspect`) or env file, and pluginlake reads them straight into its settings, so they are not in the environment of the API or the code server either.
The one exception is Dagster: `dagster.yaml` can only read its storage password from `DAGSTER_PG_PASSWORD`, so the Dagster processes have it in their environment (see below).

### Secrets

The dev and production compose provide the secrets differently, because compose only supports file secrets in services with a read-only root filesystem (the production stack, see [security](security.md)).

**Production: one file per secret.** The station directory has a `secrets/` directory with one file per password; compose bind-mounts each file read-only at `/run/secrets/<name>`:

```yaml
services:
  postgres:
    read_only: true
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password

secrets:
  postgres_password:
    file: ./secrets/postgres_password   # relative to the station directory
```

Without Swarm, compose ignores `uid`/`gid`/`mode` for file secrets and the container sees the host file with its host permissions.
The services run as other users than the operator, so the files are `0644` inside a `0700` directory: other host users cannot reach them, the containers read them through the bind mount, which does not cross the directory.
`pluginlake up` checks this: it refuses a `secrets/` directory that other users can access and missing or empty secret files, and warns about files the containers cannot read.

**Dev: environment-sourced secrets.** The dev compose keeps a writable root filesystem and declares its passwords as environment-sourced secrets:

```yaml
secrets:
  postgres_password:
    environment: POSTGRES_PASSWORD   # read by docker compose from deploy/compose/.env
```

`docker compose` reads the value from its own environment and copies it into the container as `/run/secrets/<name>`.
The env file is never passed to `env_file:`, so the value is not in any container's environment.

How each service reads its secret:

| Service | Secret file | How |
|---------|-------------|-----|
| pluginlake API, code server, Dagster (DuckLake) | `ducklake_pg_password` | `DuckLakeSettings` (pydantic `secrets_dir`) |
| Dagster webserver, daemon, code server, `dagster dev` | `dagster_pg_password` | `DagsterPostgresSettings` (in `pluginlake.deploy.dagster_env`), exported as `DAGSTER_PG_PASSWORD` by that launcher |
| postgres, marquez-db | `postgres_password`, `marquez_db_password` | `POSTGRES_PASSWORD_FILE`, native in the image |
| marquez | `marquez_db_password` | Exported as `POSTGRES_PASSWORD` for the Marquez process only by its compose entrypoint (`marquez.yml` reads the environment) |
| postgres-exporter | `postgres_exporter_password` | `DATA_SOURCE_PASS_FILE`, native in the image |
| Prometheus | `prometheus_remote_write_password` | `basic_auth.password_file`, set by its entrypoint |

pluginlake settings classes set `secrets_dir=secrets_dir()` (`pluginlake.config`), which is `/run/secrets` when it exists.
pydantic then reads a field from the file named after its environment variable in lowercase, e.g. `DUCKLAKE_PG_PASSWORD` from `/run/secrets/ducklake_pg_password`.
Environment variables and `.env` take precedence over secret files, so keep passwords out of every env file a container loads; locally, without `/run/secrets`, the settings read the root `.env` as before.

`pluginlake.deploy.dagster_env` is the image entrypoint of the production Dagster webserver/daemon, wraps the production code server and wraps `dagster dev` in the dev image.
The code server needs the password too: runs execute there (`DefaultRunLauncher` with a gRPC code location) and write their events to the Dagster instance.
It loads `DagsterPostgresSettings`, sets `DAGSTER_PG_PASSWORD` for the Dagster process only and `exec`s the command; with `--ensure-db` it first creates the Dagster database if it is missing.
The launcher only depends on pydantic-settings, so the production webserver/daemon image does not install pluginlake: it installs the `dagster-webserver` dependency group and runs the launcher as a single file (`python /app/dagster_env.py`).
`--ensure-db` needs pluginlake and is only used in the dev image.

### Dagster instance config and run logs

The dev stack uses `config/dagster/dagster.yaml`; the production webserver/daemon image uses `config/dagster/dagster.production.yaml` as its `dagster.yaml`.
The daemon passes this instance config to runs, so the code server needs no copy of its own.
The two files differ only in compute logs: production uses `NoOpComputeLogManager`, because capturing stdout/stderr needs `tail`, which the hardened runtime images lack.
In production, `context.log` messages are stored in Postgres and shown in the Dagster UI; stdout/stderr of steps only appear in the code-server container log (`docker compose logs dagster-code-server`).
Telemetry is disabled in both files.

### Container logs

The production compose rotates the log of every container (`x-logging` anchor): Docker's `json-file` driver with at most 5 files of 10 MB per container, so up to 50 MB is kept on the host.
Without it, Docker keeps logs without limit for as long as the container exists.
Step stdout/stderr ends up in the `dagster-code-server` log, and a `print(df)` there writes data rows; do not print data, and change the limits in the stack's `docker-compose.yaml` if the station needs a shorter or longer retention.

### Development: `deploy/compose/.env`

Docker Compose automatically loads `.env` from the directory of the compose file, for interpolation and as the source of the secrets.
Only compose reads it; the containers never load it.

```dotenv
# deploy/compose/.env (from deploy/compose/.env.example)
POSTGRES_USER=dagster
POSTGRES_PASSWORD=dagster
PROMETHEUS_REMOTE_WRITE_PASSWORD=
```

The dev stack uses the Postgres superuser for every service, so `POSTGRES_PASSWORD` is the only database secret.
`pluginlake up` passes an empty `PROMETHEUS_REMOTE_WRITE_PASSWORD` when monitoring is enabled and the variable is not defined.

The dev containers do not load the root `.env`; it is only for `just dev-local` (no Docker) and keeps its passwords for that.
Container settings are set explicitly in the compose file; extra non-secret settings (e.g. for a project) can go in `deploy/compose/.env.containers`, or another file selected with `PLUGINLAKE_ENV_FILE`.
The dev stack mounts its one `postgres_password` secret under the names the settings read (`dagster_pg_password`, `ducklake_pg_password`).

### Production: `.env.production` and `secrets/`

Production splits configuration from secrets, both in the station directory (next to `pluginlake.toml`):

| Path | Read by | Contains |
|------|---------|----------|
| `.env.production` | containers (`env_file`) and compose | users, database names, hosts, ports |
| `secrets/<name>` | the services that mount the secret | `postgres_password`, `dagster_pg_password`, `ducklake_pg_password`; with monitoring `postgres_exporter_password` and `prometheus_remote_write_password` (may be empty; `pluginlake up` creates it empty); with lineage `marquez_db_password` |

The template for `.env.production` is `src/pluginlake/deploy/stack/templates/env.production.example`; [deploying a station](deploying-a-station.md) shows how to create the secrets.
For `just up` from a checkout, put both in `deploy/compose/` (gitignored).

### Comparison

| Approach | Where secrets live | Visible in `docker inspect` | Encryption | Best for |
|----------|-------------------|----------------------------|------------|----------|
| `environment:` in compose | Compose file (committed) | Yes | No | Never use for real secrets |
| `.env` + `${VAR}` in `environment:` | `.env` file (gitignored) | Yes | No | Not used for secrets |
| `env_file:` | Separate file (gitignored) | Yes | No | Non-secret configuration |
| Compose `secrets:` (environment source) | Compose-only env file, copied to `/run/secrets/` | No | No | Our dev compose |
| Compose `secrets:` (file source) | One file per secret, bind-mounted at `/run/secrets/` | No | No | Our production stack (read-only containers) |
| Swarm `secrets:` | Raft log (encrypted) | No | Yes | Swarm production |
| External vault | Vault/KMS | No | Yes | Kubernetes / regulated environments |

Compose secrets are not encrypted at rest on the host: protect the secret files with the directory permissions (`chmod 700 secrets`).
Kubernetes and Swarm mount secrets as files too, so the same `/run/secrets/<name>` files work with the platform's secret store.

### What goes where

| Variable | Secret? | Notes |
|----------|---------|-------|
| `DAGSTER_HOME` | No | Always `/app/config/dagster`, set in Dockerfile |
| `DAGSTER_MODULE` | No | Which Python module to load |
| `DAGSTER_PG_HOST` | No | Service name within the Docker network |
| `DAGSTER_PG_USER` | No | `.env.production` |
| `POSTGRES_PASSWORD` | **Yes** | Secret `postgres_password` (production: `secrets/postgres_password`) |
| `DAGSTER_PG_PASSWORD` | **Yes** | Secret `dagster_pg_password` (production; dev uses `postgres_password`) |
| `DUCKLAKE_PG_PASSWORD` | **Yes** | Secret `ducklake_pg_password` (production; dev uses `postgres_password`) |
| `POSTGRES_EXPORTER_PASSWORD` | **Yes** | Secret `postgres_exporter_password` (production; dev uses `postgres_password`) |
| `PROMETHEUS_REMOTE_WRITE_PASSWORD` | **Yes** | Secret `prometheus_remote_write_password`; never in `.env.monitoring` |
| `MARQUEZ_DB_PASSWORD` | **Yes** | Secret `marquez_db_password` (production; dev sets it in `deploy/compose/.env`) |

## File layout

```text
src/pluginlake/deploy/stack/              # Production stack, shipped in the package
├── docker-compose.yaml                   # Hardened, digest-pinned production compose
├── images.json                           # Images lock, written by the release workflow
├── marquez/marquez.yml                   # Marquez API config (profile `lineage`)
├── monitoring/prometheus/                # Prometheus entrypoint, config and scrape jobs
└── templates/                            # env.production.example, env.monitoring.example
deploy/
├── compose/
│   ├── .env                              # Dev compose env and secret values (gitignored)
│   ├── .env.example                      # Template for dev (committed)
│   ├── .env.containers                   # Optional extra non-secret settings for dev containers (gitignored)
│   ├── .env.production, secrets/         # Only for `just up` from a checkout (gitignored)
│   ├── .env.monitoring                   # Prometheus remote-write URL and username (gitignored)
│   ├── smoke.env / smoke.secrets.env     # Throwaway config and secrets for the smoke test (committed)
│   ├── docker-compose.dev.yaml           # Dev: single dagster container + postgres + pluginlake + UI
│   ├── docker-compose.build.yaml         # Builds the production images for `just up`
│   ├── docker-compose.smoke.yaml         # Isolated volumes for the smoke test
│   └── docker-compose.central.yaml       # Central dashboard (separate compose)
└── docker/
    ├── api.Dockerfile                    # Image `api`: FastAPI + code-server (multi-stage)
    ├── dagster-webserver.Dockerfile      # Image `dagster-webserver`: webserver + daemon (multi-stage)
    ├── ui.Dockerfile                     # Images `ui-datastation`, `ui-central` (multi-stage)
    ├── dagster.dev.Dockerfile            # Dev all-in-one dagster (single stage)
    ├── pluginlake.dev.Dockerfile         # Dev FastAPI (single stage)
    └── ui.dev.Dockerfile                 # Dev dashboards, APP=datastation|central (hot reload)
```
