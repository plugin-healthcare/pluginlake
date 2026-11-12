# Docker guide

This guide covers how pluginlake uses Docker for development and production, including image strategy, multi-stage builds, and secrets management.

## Container architecture

pluginlake uses separate containers for each concern:

| Container | Dockerfile | Purpose |
|-----------|-----------|---------|
| **postgres** | `dhi.io/postgres:17-alpine3.24` (pre-built) | Dagster metadata + DuckLake catalog |
| **dagster-webserver** | `dagster-webserver.Dockerfile` | Dagster web UI |
| **dagster-daemon** | `dagster-webserver.Dockerfile` | Schedules, sensors, run queue |
| **dagster-code-server** | `pluginlake.Dockerfile` | Asset definitions served via gRPC |
| **pluginlake** | `pluginlake.Dockerfile` | FastAPI service |
| **pluginlake-ui** | `ui.Dockerfile` (`APP=datastation`) | Datastation Streamlit dashboard |
| **pluginlake-central** | `ui.Dockerfile` (`APP=central`) | Central aggregation dashboard |
| **prometheus** | `quay.io/prometheus/prometheus` (pre-built) | Metrics store |
| **postgres-exporter** | `quay.io/prometheuscommunity/postgres-exporter` (pre-built) | Postgres metrics |
| **cadvisor** | `ghcr.io/google/cadvisor` (pre-built) | Container metrics |
| **marquez-db** | `dhi.io/postgres:17-alpine3.24` (pre-built) | Marquez database |
| **marquez** | `marquezproject/marquez:0.51.1` (pre-built) | OpenLineage receiver API |
| **marquez-web** | `marquezproject/marquez-web:0.51.1` (pre-built) | Lineage web UI, host loopback only |

Prometheus and Marquez are core components and always start with the production compose; `[station]` and `[monitoring]` in `pluginlake.toml` set the lineage namespace, the station label, cAdvisor and remote write, see the [monitoring guide](monitoring.md).

In development, `dagster.dev.Dockerfile` replaces the webserver, daemon, and code-server with a single all-in-one container running `dagster dev`. The UI containers use `ui.dev.Dockerfile` with hot reload. Both dashboards share one Dockerfile; the build arguments `APP` (`datastation` or `central`) and `PORT` (8501 or 8502) select the dashboard.

## Building and running

### Development

```bash
just dev-up        # Build and start all dev containers
just dev-down      # Stop and remove dev containers
```

This uses `deploy/compose/docker-compose.dev.yaml`. Source code is volume-mounted into the containers, so changes are picked up immediately without rebuilding.

### Production

```bash
just up            # Prepare the node from pluginlake.toml, then build and start all production containers
just up-dev        # The same with development defaults (pluginlake.localhost, secrets also in .pluginlake/secrets.env)
just down          # Stop and remove production containers
```

This uses `deploy/compose/docker-compose.yaml`.
Images are fully self-contained, with no volume mounts for source code.
The stack sits behind Traefik, oauth2-proxy and Zitadel (see [Edge](#edge)).

### Building individual images

```bash
# From the project root:
docker build -f deploy/docker/pluginlake.Dockerfile -t pluginlake .
docker build -f deploy/docker/dagster-webserver.Dockerfile -t dagster-webserver .
```

The build context is always the project root (`../../` in the compose files) because Dockerfiles need access to `pyproject.toml`, `uv.lock`, `src/`, and `config/`.

## Projects and database provisioning

The development images (`pluginlake.dev.Dockerfile` and `dagster.dev.Dockerfile`) share the entrypoint `deploy/docker/entrypoint.sh`.
It runs before the service starts and reads `PLUGINLAKE_PROJECTS`: whitespace-separated `uv pip install` arguments for the project packages to install.
The production images used by `just up` do not run this entrypoint, so the variable has no effect there.

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

All Dockerfiles use hardened images from `dhi.io/` instead of the default Docker Hub images:

```dockerfile
FROM dhi.io/python:3.13-debian13-dev AS builder    # Build stage
FROM dhi.io/python:3.13-debian13                    # Runtime stage
FROM dhi.io/postgres:17-alpine3.24                  # Database
```

**Why hardened images?**

Standard images from Docker Hub (e.g. `python:3.13-slim`) ship with the full upstream package set and default configurations. Hardened images are rebuilt with security fixes applied, unnecessary packages removed, and restrictive defaults set. This reduces the attack surface and helps meet compliance requirements in healthcare environments.

**Prerequisites:**

Hardened images are distributed through Docker Hub and require authentication to pull. Before building any of the project's Docker images:

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
COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/
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
RUN uv sync --frozen --no-dev
```

**Stage 2 — Runtime:** Copy only the virtual environment and source code into the minimal runtime image:

```dockerfile
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"
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

## Edge

The production compose publishes only the ports 80 and 443 of Traefik.
Traefik terminates TLS and sends every application host through oauth2-proxy forward auth, with Zitadel as identity provider.

```mermaid
flowchart LR
    user([Browser]) --> traefik[Traefik 80/443]
    traefik -- forward auth --> proxy[oauth2-proxy]
    proxy -- OIDC --> zitadel[Zitadel + login UI]
    traefik --> api[api. pluginlake]
    traefik --> dagster[dagster.]
    traefik --> dash[dashboard.]
    traefik --> marquez[marquez.]
    traefik --> prom[prometheus.]
    zitadel --> pg[(Postgres)]
    api --> pg
```

| Host | Service | Protected |
|------|---------|-----------|
| `<domain>` | Start page with links to the web interfaces below | Yes |
| `auth.<domain>` | Zitadel and its login UI | No (it is the sign-in) |
| `api.<domain>` | pluginlake API | Yes |
| `dagster.<domain>` | Dagster webserver | Yes |
| `dashboard.<domain>` | Streamlit dashboard | Yes |
| `marquez.<domain>` | Marquez web | Yes |
| `prometheus.<domain>` | Prometheus | Yes |

`[node] domain` in `pluginlake.toml` sets the domain.
`just setup --dev` uses `pluginlake.localhost`, which resolves to the local machine in browsers, and creates a certificate for it with [mkcert](https://github.com/FiloSottile/mkcert) in `tls/` of the data folder.
Install mkcert first; setup runs `mkcert -install` once so browsers trust it, and oauth2-proxy trusts the same root CA.

Traefik reads its certificate from `tls/tls.yaml` in the data folder.
For a real domain, put your own `tls.yaml` with `certFile` and `keyFile` entries (paths below `/tls`) and the certificate files there; setup does not overwrite it.

On first start `pluginlake-init` waits for Zitadel, creates the project and the OIDC application with the Management API and writes the oauth2-proxy configuration to the `bootstrap` folder, so there are no manual steps.
The first admin is `ZITADEL_ADMIN_USERNAME` with the generated password in `secrets/zitadel_admin_password`.
Zitadel always forces a new password at the first login.
All other users, passwords and access are managed in Zitadel.
The choice of Zitadel, with Keycloak as the fallback, is described in [ADR-011](../decisions/adr-011-identity-provider.md).

All protected hosts share one oauth2-proxy and one session cookie on `.<domain>`, so you sign in once, for example on the start page, and open every application without signing in again.
All applications behind the proxy therefore trust the same session.

Access is per application.
`pluginlake-init` creates a Zitadel project role for each application (`api`, `dagster`, `dashboard`, `marquez`, `prometheus`) and gives the first admin all of them.
A user only opens an application when they have the role with that name, otherwise Traefik answers 403, and the start page only shows the links the user has a role for.
Grant roles to other users as user grants on the project `pluginlake` in the Zitadel console.
The roles reach oauth2-proxy as a `groups` claim.
Zitadel calls the service `zitadel-groups-hook` (a Zitadel Actions v2 call target that `pluginlake-init` creates) while it builds the token and the userinfo, and the service answers with the roles as a list.
The target fails closed: when the hook is down or the signature check fails, Zitadel issues no token and nobody can sign in.
The hook checks the signature with a key that `pluginlake-init` writes to the `bootstrap` folder.
Zitadel blocks targets in private address ranges by default, so `zitadel-api` has `ZITADEL_HTTPCLIENT_DENYLIST` set to the default list without `172.16.0.0/12`, which is the range of the Docker networks.
As a result `zitadel-api` can reach containers on its own networks, and only `edge-net` hosts can reach `zitadel-api`.
Adjust that list when your Docker networks use another private range.
In Zitadel the loginname is `<username>@<organisation>.auth.<domain>`, for example `admin@zitadel.auth.pluginlake.localhost`.

Traefik uses the file provider and has no access to the Docker socket.
Postgres and the other databases are only on the internal network `db-net`.
Nuts and DPoP endpoints that must bypass forward auth are added with the Nuts work (#127).

## Environment variables and secrets

### The problem

Containers need configuration (database host, ports) and secrets (passwords, API keys). These should not be hardcoded in Dockerfiles or compose files, and secrets must never be committed to version control.

Configuration is passed as environment variables. Passwords are Docker Compose secrets, mounted as files under `/run/secrets/`.
They are not part of any container's configuration (`docker inspect`) or env file, and pluginlake reads them straight into its settings, so they are not in the environment of the API or the code server either.
The one exception is Dagster: `dagster.yaml` can only read its storage password from `DAGSTER_PG_PASSWORD`, so the Dagster processes have it in their environment (see below).

### Secrets

Both compose files declare their passwords as Docker secrets that pluginlake and the databases read from `/run/secrets/<name>`.
The dev compose fills them from the compose-only `deploy/compose/.env`.
The production compose uses one file per secret in `${PLUGINLAKE_HOME}/secrets`, generated by `pluginlake setup` (see below).

```yaml
services:
  postgres:
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password

secrets:
  postgres_password:
    file: ${PLUGINLAKE_HOME}/secrets/postgres_password   # production
    # environment: POSTGRES_PASSWORD                     # dev: read by docker compose
```

Without Swarm, compose bind-mounts a `file:` secret with its host owner and mode and ignores `uid` and `mode`.
In production every container runs as the host user that owns the secret files (mode `0400`), so the files are readable by the services and by nobody else.
Environment-sourced secrets with a `uid` do not work with a host user on the hardened images, because compose then looks up the user with `getent`, which these images do not ship.

How each service reads its secret:

| Service | Secret file | How |
|---------|-------------|-----|
| pluginlake API, code server, Dagster (DuckLake) | `ducklake_pg_password` | `DuckLakeSettings` (pydantic `secrets_dir`) |
| Dagster webserver, daemon, code server, `dagster dev` | `dagster_pg_password` | `DagsterPostgresSettings` (in `pluginlake.deploy.dagster_env`), exported as `DAGSTER_PG_PASSWORD` by that launcher |
| postgres | `postgres_password` | `POSTGRES_PASSWORD_FILE`, native in the image |
| postgres-exporter | `postgres_exporter_password` | `DATA_SOURCE_PASS_FILE`, native in the image |
| Prometheus | `prometheus_remote_write_password` | `basic_auth.password_file`, set by its entrypoint |
| Zitadel | `zitadel_masterkey`, `zitadel_config.yaml` (database password), `zitadel_admin_password` and `zitadel_steps.yaml` (first admin) | `--masterkeyFile`, `--config`, `--steps` |
| Zitadel login UI | `zitadel_cookie_secret` | The entrypoint exports it from the file before starting the login UI |
| Marquez | `marquez_db_password` | The entrypoint exports it from the file before starting Marquez |

No production service gets a secret through its environment configuration: services that can only read environment variables get it exported from the mounted file by their entrypoint, so it does not appear in `docker inspect`.

pluginlake settings classes set `secrets_dir=secrets_dir()` (`pluginlake.config`), which is `/run/secrets` when it exists.
pydantic then reads a field from the file named after its environment variable in lowercase, e.g. `DUCKLAKE_PG_PASSWORD` from `/run/secrets/ducklake_pg_password`.
Environment variables and `.env` take precedence over secret files, so keep passwords out of every env file a container loads; locally, without `/run/secrets`, the settings read the root `.env` as before.

`pluginlake.deploy.dagster_env` is the image entrypoint of the production Dagster webserver/daemon, wraps the production code server and wraps `dagster dev` in the dev image.
The code server needs the password too: runs execute there (`DefaultRunLauncher` with a gRPC code location) and write their events to the Dagster instance.
It loads `DagsterPostgresSettings`, sets `DAGSTER_PG_PASSWORD` for the Dagster process only and `exec`s the command; with `--ensure-db` it first creates the Dagster database if it is missing.
The launcher only depends on pydantic-settings, so the production webserver/daemon image does not install pluginlake: it installs the `dagster-webserver` dependency group and runs the launcher as a single file (`python /app/dagster_env.py`).
`--ensure-db` needs pluginlake and is only used in the dev image.

Container settings are set explicitly in the compose file; extra non-secret settings (e.g. for a project) can go in `deploy/compose/.env.containers`, or another file selected with `PLUGINLAKE_ENV_FILE`.
The dev stack mounts its one `postgres_password` secret under the names the settings read (`dagster_pg_password`, `ducklake_pg_password`).

### Production: `pluginlake.toml` and the data folder

The production compose has no defaults and no env files.
Node settings (domain, first admin name) are in the `[node]` section of `pluginlake.toml`, and fixed names such as the database roles are constants in the compose file.

| What | Where | Created by |
|------|-------|------------|
| Node settings | `[node]` in `pluginlake.toml` | You |
| uid, gid, data folder and domain for compose | `${PLUGINLAKE_HOME}/compose.env` | `pluginlake setup`, run by `just up` |
| Secrets | `${PLUGINLAKE_HOME}/secrets/` (one file per secret, mode `0400`) | `pluginlake setup`. The secrets, their kind and the services that mount them are listed in `src/pluginlake/deploy/secrets.toml` |
| Database roles and databases | Postgres | `pluginlake-db-init` (`python -m pluginlake.deploy.init_databases`) |

Compose reads the host user, the data folder and the domain while it parses the file, before any container runs.
`just up` therefore first runs `pluginlake setup` in a container as the host user, without network and with a read-only root file system.
`pluginlake setup` creates the folders and the secrets that do not exist yet and writes `compose.env`; `just up` then starts the stack with that file.
Without `--dev` a `[node] domain` is required, with `--dev` (`just up-dev`) the domain is `pluginlake.localhost` and the plain secrets are also written to `secrets.env`, mode `0600`.
`pluginlake setup` can also run on the host (`uv run pluginlake setup --home .pluginlake`).
Existing secrets are never overwritten, so `just up` is safe to run again.
Secrets are not rotated by deleting files: removing a database password file without changing it in Postgres locks the service out.

`pluginlake-db-init` is the only service besides Postgres that uses the Postgres superuser.
It creates a role and a database per service (`dagster`, `ducklake`, `zitadel`) and a read-only `pg_monitor` role for postgres-exporter, each with its own generated password.
Every other service only receives the credentials of its own role.

### Data folder and host user

All containers run as the host user (`PLUGINLAKE_UID`, `PLUGINLAKE_GID`) and keep their data in bind mounts below `PLUGINLAKE_HOME` (default `.pluginlake` in the repository root; set the environment variable `PLUGINLAKE_HOME` before `just up` to use another folder).

```text
.pluginlake/
├── compose.env    # uid, gid, home and domain for compose, written by pluginlake setup
├── secrets.env    # plain secrets for development, only with --dev
├── secrets/       # secrets written by pluginlake setup, mode 0700
├── bootstrap/     # tokens and oauth2-proxy config written by Zitadel and pluginlake-init, mode 0700
├── postgres/      # database cluster
├── marquez-db/    # lineage database
├── prometheus/    # metrics
├── data/          # DuckLake storage and Dagster state
└── passwd         # passwd entry for the host user, mounted into the Postgres containers
```

The compose file declares no named volumes, so `docker compose down -v` and `docker volume prune` do not remove data.
Keep this folder in one place instead of spreading it over `~/.config` and `~/.local`; back it up as a whole.

Run this on Linux.
Docker Desktop on macOS maps the ownership of bind mounts, which makes Postgres refuse its data folder.

### Dagster instance config and run logs

The dev stack uses `config/dagster/dagster.yaml`; the production webserver/daemon image uses `config/dagster/dagster.production.yaml` as its `dagster.yaml`.
The daemon passes this instance config to runs, so the code server needs no copy of its own.
The two files differ only in compute logs: production uses `NoOpComputeLogManager`, because capturing stdout/stderr needs `tail`, which the hardened runtime images lack.
In production, `context.log` messages are stored in Postgres and shown in the Dagster UI; stdout/stderr of steps only appear in the code-server container log (`docker compose logs dagster-code-server`).
Telemetry is disabled in both files.

### Container logs

The production compose rotates the log of every container (`x-logging` anchor): Docker's `json-file` driver with at most 5 files of 10 MB per container, so up to 50 MB is kept on the host.
Without it, Docker keeps logs without limit for as long as the container exists.
Step stdout/stderr ends up in the `dagster-code-server` log, and a `print(df)` there writes data rows; do not print data, and change the limits in `docker-compose.yaml` if the station needs a shorter or longer retention.

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

### Comparison

| Approach | Where secrets live | Visible in `docker inspect` | Encryption | Best for |
|----------|-------------------|----------------------------|------------|----------|
| `environment:` in compose | Compose file (committed) | Yes | No | Never use for real secrets |
| `.env` + `${VAR}` in `environment:` | `.env` file (gitignored) | Yes | No | Not used for secrets |
| `env_file:` | Separate file (gitignored) | Yes | No | Non-secret configuration |
| Compose `secrets:` (environment source) | Compose-only env file, copied to `/run/secrets/` | No | No | Our dev compose |
| Compose `secrets:` (file source) | Private folder owned by the service user, mounted at `/run/secrets/` | No | No | Our production compose |
| Swarm `secrets:` | Raft log (encrypted) | No | Yes | Swarm production |
| External vault | Vault/KMS | No | Yes | Kubernetes / regulated environments |

Compose secrets are not encrypted at rest on the host: protect the secrets with file permissions (`0400` files in a `0700` folder).
Kubernetes and Swarm mount secrets as files too, so the same `/run/secrets/<name>` files work with the platform's secret store.

### What goes where

| Variable | Secret? | Notes |
|----------|---------|-------|
| `DAGSTER_HOME` | No | Always `/app/config/dagster`, set in Dockerfile |
| `DAGSTER_MODULE` | No | Which Python module to load |
| `DAGSTER_PG_HOST` | No | Service name within the Docker network |
| `DAGSTER_PG_USER` | No | Constant in the compose file |
| `POSTGRES_PASSWORD` | **Yes** | Secret `postgres_password` (Postgres superuser, `pluginlake-db-init` only in production) |
| `DAGSTER_PG_PASSWORD` | **Yes** | Secret `dagster_pg_password` (production; dev uses `postgres_password`) |
| `DUCKLAKE_PG_PASSWORD` | **Yes** | Secret `ducklake_pg_password` (production; dev uses `postgres_password`) |
| `POSTGRES_EXPORTER_PASSWORD` | **Yes** | Secret `postgres_exporter_password` (production; dev uses `postgres_password`) |
| `PROMETHEUS_REMOTE_WRITE_PASSWORD` | **Yes** | Secret `prometheus_remote_write_password`; never in `.env.monitoring` |

## File layout

```text
deploy/
├── compose/
│   ├── .env                          # Dev compose env and secret values (gitignored)
│   ├── .env.example                  # Template for dev (committed)
│   ├── .env.containers               # Optional extra non-secret settings for dev containers (gitignored)
│   ├── traefik/                      # Traefik static config and routes (committed)
│   ├── .env.monitoring               # Prometheus remote-write URL and username (gitignored)
│   ├── .env.monitoring.example       # Template for Prometheus settings (committed)
│   ├── smoke.env / smoke.secrets.env # Throwaway config and secrets for the smoke test (committed)
│   ├── docker-compose.dev.yaml       # Dev: single dagster container + postgres + pluginlake + UI
│   ├── docker-compose.central.yaml   # Central dashboard (separate compose)
│   └── docker-compose.yaml           # Prod: separate webserver, daemon, code-server
├── docker/
│   ├── dagster.dev.Dockerfile         # Dev all-in-one dagster (single stage)
│   ├── dagster-webserver.Dockerfile   # Prod webserver + daemon (multi-stage)
│   ├── pluginlake.dev.Dockerfile      # Dev FastAPI (single stage)
│   ├── pluginlake.Dockerfile          # Prod FastAPI + code-server (multi-stage)
│   ├── ui.dev.Dockerfile              # Dev dashboards, APP=datastation|central (hot reload)
│   └── ui.Dockerfile                  # Prod dashboards, APP=datastation|central (multi-stage)
└── monitoring/
    └── prometheus/
        ├── entrypoint.sh              # Renders the config (labels, cAdvisor, remote_write)
        ├── prometheus.yml             # Global config
        └── scrape.d/                  # One scrape job per file
```
