# Deployment Guide

This guide covers deploying pluginlake as a multi-container Docker Compose stack.
You can use the `pluginlake` CLI to automate setup, or configure everything manually.

## Quick start (with CLI)

```bash
# Install pluginlake (from the repo root)
uv pip install -e .

# Initialize a new instance
pluginlake init

# Start the stack
pluginlake up --instance ds-001

# Start with the Dagster UI dashboard
pluginlake up --instance ds-001 --profile ui

# Check status
pluginlake status --instance ds-001

# Stop
pluginlake down --instance ds-001
```

## Manual setup (without CLI)

If you prefer not to install the CLI, follow these steps.

### 1. Create the directory structure

pluginlake uses XDG-compliant paths. Replace `<id>` with your datastation identifier (e.g. `ds-001`):

```bash
# Config
mkdir -p ~/.config/pluginlake/<id>

# Data
mkdir -p ~/.local/share/pluginlake/<id>/storage

# State (logs, dagster runtime)
mkdir -p ~/.local/state/pluginlake/<id>/dagster
mkdir -p ~/.local/state/pluginlake/<id>/logs/compute
mkdir -p ~/.local/state/pluginlake/<id>/logs/dagster
```

### 2. Create the .env file

Copy the template and fill in values:

```bash
cp deploy/templates/.env.template ~/.config/pluginlake/<id>/.env
```

Required values to set:
- `DATASTATION_ID` — your instance identifier
- `DATASTATION_NAME` — human-readable name
- `POSTGRES_PASSWORD` — generate with `openssl rand -base64 32`
- `PUID` / `PGID` — your user/group IDs (`id -u` / `id -g`)
- `PLUGINLAKE_CONFIG_DIR` — `~/.config/pluginlake/<id>`
- `PLUGINLAKE_DATA_DIR` — `~/.local/share/pluginlake/<id>`
- `PLUGINLAKE_STATE_DIR` — `~/.local/state/pluginlake/<id>`

Derived values (set these to match your password):
- `DAGSTER_PG_USER`, `DAGSTER_PG_PASSWORD` — same as POSTGRES_USER/PASSWORD
- `DUCKLAKE_PG_USER`, `DUCKLAKE_PG_PASSWORD` — same as POSTGRES_USER/PASSWORD

### 3. Copy Dagster configuration

```bash
cp deploy/templates/dagster.yaml ~/.config/pluginlake/<id>/dagster.yaml
cp deploy/templates/workspace.yaml ~/.config/pluginlake/<id>/workspace.yaml
```

These files use environment variables for database connection, so they work without modification.

### 4. Start the stack

```bash
docker compose \
  -f deploy/compose/docker-compose.yaml \
  --env-file ~/.config/pluginlake/<id>/.env \
  -p pluginlake-<id> \
  up -d --build
```

To include the Dagster UI:

```bash
docker compose \
  -f deploy/compose/docker-compose.yaml \
  --env-file ~/.config/pluginlake/<id>/.env \
  -p pluginlake-<id> \
  --profile ui \
  up -d --build
```

### 5. Verify

```bash
# Check all containers are healthy
docker compose -p pluginlake-<id> ps

# Test API
curl http://localhost:8000/health
```

## Architecture

The production stack has 5 services (6 with UI):

| Service | Role | Port |
|---------|------|------|
| postgres | Shared PostgreSQL (Dagster metadata + DuckLake catalog) | 5432 |
| dagster-code-server | User code (gRPC) — runs pipelines via DefaultRunLauncher | 4000 |
| dagster-webserver | GraphQL API + optional UI | 3000 |
| dagster-daemon | Orchestration (sensors, schedules, run coordination) | — |
| pluginlake | FastAPI data catalog API | 8000 |
| dashboard-datastation | Streamlit UI (optional, `--profile ui`) | 8501 |

### How runs execute

With `DefaultRunLauncher`, Dagster pipeline runs execute inside the **code-server** container (not the daemon).
The daemon only handles orchestration (sensors, schedules, queued run coordination).
The webserver provides the GraphQL API that the pluginlake API uses to trigger runs.

## Multi-instance support

Each instance gets its own:
- Docker Compose project name (`pluginlake-<id>`)
- PostgreSQL databases (namespaced: `dagster_<id>`, `ducklake_<id>`)
- Port allocations (auto-detected by CLI, or manually set)
- XDG directory subtree

Multiple instances can coexist on the same host.
Use `pluginlake list` to see all configured instances.

## Environment variables reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DATASTATION_ID` | — | Unique instance identifier |
| `DATASTATION_NAME` | — | Human-readable name |
| `PUID` | 1000 | Host user ID for containers |
| `PGID` | 1000 | Host group ID for containers |
| `POSTGRES_USER` | pluginlake | PostgreSQL superuser |
| `POSTGRES_PASSWORD` | — | PostgreSQL password |
| `POSTGRES_PORT` | 5432 | Host port for PostgreSQL |
| `DAGSTER_PG_DB` | dagster | Dagster database name |
| `DAGSTER_PORT` | 3000 | Host port for Dagster webserver |
| `DUCKLAKE_PG_DB` | ducklake | DuckLake database name |
| `PLUGINLAKE_SERVER_PORT` | 8000 | Host port for API |
| `CODE_SERVER_PORT` | 4000 | Host port for code server |
| `PLUGINLAKE_CONFIG_DIR` | — | Instance config path |
| `PLUGINLAKE_DATA_DIR` | — | Instance data path |
| `PLUGINLAKE_STATE_DIR` | — | Instance state path |
