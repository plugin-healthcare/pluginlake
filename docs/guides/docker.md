# Docker guide

This guide covers how pluginlake uses Docker for development and production, including image strategy, multi-stage builds, and secrets management.

## Container architecture

pluginlake uses separate containers for each concern:

| Container | Dockerfile | Purpose |
|-----------|-----------|---------|
| **postgres** | `dhi.io/postgres:17-alpine3.22` (pre-built) | Dagster metadata storage |
| **dagster-webserver** | `dagster-webserver.Dockerfile` | Dagster web UI |
| **dagster-daemon** | `dagster-webserver.Dockerfile` | Schedules, sensors, run queue |
| **dagster-code-server** | `pluginlake.Dockerfile` | Asset definitions served via gRPC |
| **pluginlake** | `pluginlake.Dockerfile` | FastAPI service |

In development, `dagster.dev.Dockerfile` replaces the webserver, daemon, and code-server with a single all-in-one container running `dagster dev`.

## Building and running

### Development

```bash
just dev-up        # Build and start all dev containers
just dev-down      # Stop and remove dev containers
```

This uses `deploy/compose/docker-compose.dev.yaml`. Source code is volume-mounted into the containers, so changes are picked up immediately without rebuilding.

### Production

```bash
just up            # Build and start all production containers
just down          # Stop and remove production containers
```

This uses `deploy/compose/docker-compose.yaml`. Images are fully self-contained — no volume mounts for source code.

### Building individual images

```bash
# From the project root:
docker build -f deploy/docker/pluginlake.Dockerfile -t pluginlake .
docker build -f deploy/docker/dagster-webserver.Dockerfile -t dagster-webserver .
```

The build context is always the project root (`../../` in the compose files) because Dockerfiles need access to `pyproject.toml`, `uv.lock`, `src/`, and `config/`.

## Hardened base images

All Dockerfiles use hardened images from `dhi.io/` instead of the default Docker Hub images:

```dockerfile
FROM dhi.io/python:3.13-debian13-dev AS builder    # Build stage
FROM dhi.io/python:3.13-debian13                    # Runtime stage
FROM dhi.io/postgres:17-alpine3.22                  # Database
```

**Why hardened images?**

Standard images from Docker Hub (e.g. `python:3.13-slim`) ship with the full upstream package set and default configurations. Hardened images are rebuilt with security fixes applied, unnecessary packages removed, and restrictive defaults set. This reduces the attack surface and helps meet compliance requirements in healthcare environments.

**Prerequisites:**

Hardened images are distributed through Docker Hub and require authentication to pull. Before building any of the project's Docker images:

1. Create an account at [hub.docker.com](https://hub.docker.com) if you don't have one.
2. Log in from the CLI:
   ```bash
   docker login
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

## Environment variables and secrets

### The problem

Containers need configuration (database host, ports) and secrets (passwords, API keys). These should not be hardcoded in Dockerfiles or compose files, and secrets must never be committed to version control.

### Development: `.env` file

Docker Compose automatically loads a `.env` file from the same directory as the compose file. The dev setup uses variable interpolation:

```yaml
# docker-compose.dev.yaml
services:
  postgres:
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
```

The actual values live in `deploy/compose/.env`:

```dotenv
POSTGRES_USER=dagster
POSTGRES_PASSWORD=dagster
```

A committed `.env.example` documents which variables are needed. The `.env` file itself is gitignored.

### Production: `env_file`

The production compose file uses `env_file` to load variables from a separate file:

```yaml
# docker-compose.yaml
services:
  postgres:
    env_file: .env.production
```

Operators create `.env.production` on the server from the committed `.env.production.example` template and fill in real credentials. This file is gitignored and should be readable only by the user running Docker.

```bash
cp deploy/compose/.env.production.example deploy/compose/.env.production
chmod 600 deploy/compose/.env.production
# Edit with real values
```

### Docker Compose secrets (Swarm mode)

Docker has a built-in secrets mechanism that mounts secret values as files at `/run/secrets/<name>` inside containers, rather than exposing them as environment variables. This is more secure because:

- Secrets are encrypted at rest and in transit
- They don't appear in `docker inspect` output
- They're stored in a tmpfs mount, never written to disk in the container

```yaml
# Example (requires Docker Swarm or docker compose with secrets support)
services:
  postgres:
    secrets:
      - pg_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/pg_password

secrets:
  pg_password:
    file: ./secrets/pg_password.txt    # For compose
    # external: true                   # For Swarm (managed via `docker secret create`)
```

The application reads the password from the file instead of an environment variable. Postgres and many other images support the `_FILE` suffix convention (e.g. `POSTGRES_PASSWORD_FILE`) for this purpose.

**Why we don't use it (yet):**

- `docker compose` (non-Swarm) supports file-based secrets but the mechanism is essentially the same as `env_file` — the file is bind-mounted into the container. There is no encryption or access control beyond filesystem permissions.
- True secret isolation requires Docker Swarm mode or an external vault (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault).
- For our current deployment model, `env_file` with proper file permissions is sufficient. When deploying to Kubernetes, secrets are handled by the cluster's secret management.

### Comparison

| Approach | Where secrets live | Visible in `docker inspect` | Encryption | Best for |
|----------|-------------------|----------------------------|------------|----------|
| `environment:` in compose | Compose file (committed) | Yes | No | Never use for real secrets |
| `.env` + `${VAR}` | `.env` file (gitignored) | Yes | No | Local development |
| `env_file:` | Separate file (gitignored) | Yes | No | Simple production |
| Compose `secrets:` | File mount at `/run/secrets/` | No | No (file-based) | Compose production |
| Swarm `secrets:` | Raft log (encrypted) | No | Yes | Swarm production |
| External vault | Vault/KMS | No | Yes | Kubernetes / regulated environments |

### What goes where

| Variable | Secret? | Notes |
|----------|---------|-------|
| `DAGSTER_HOME` | No | Always `/app/config/dagster`, set in Dockerfile |
| `DAGSTER_MODULE` | No | Which Python module to load |
| `DAGSTER_PG_HOST` | No | Service name within the Docker network |
| `DAGSTER_PG_USER` | No | Can be in `.env` |
| `DAGSTER_PG_PASSWORD` | **Yes** | Must be in `.env` / `env_file`, never in compose |
| `POSTGRES_PASSWORD` | **Yes** | Must be in `.env` / `env_file`, never in compose |

## File layout

```
deploy/
├── compose/
│   ├── .env                          # Dev values (gitignored)
│   ├── .env.example                  # Template for dev (committed)
│   ├── .env.production               # Prod values (gitignored)
│   ├── .env.production.example       # Template for prod (committed)
│   ├── docker-compose.dev.yaml       # Dev: single dagster container + postgres + pluginlake
│   └── docker-compose.yaml           # Prod: separate webserver, daemon, code-server
└── docker/
    ├── dagster.dev.Dockerfile         # Dev all-in-one dagster (single stage)
    ├── dagster-webserver.Dockerfile   # Prod webserver + daemon (multi-stage)
    ├── pluginlake.dev.Dockerfile      # Dev FastAPI (single stage)
    └── pluginlake.Dockerfile          # Prod FastAPI + code-server (multi-stage)
```
