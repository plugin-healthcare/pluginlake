# pluginlake

Federated datalake for data stations.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — package manager
- [just](https://github.com/casey/just) — task runner
- [Docker](https://www.docker.com/) — for containerized dev/prod setups

## Quickstart

```bash
git clone https://github.com/plugin-healthcare/pluginlake.git
cd pluginlake
just init
```

### Try the example

Run the Titanic example to verify everything works:

```bash
just dev-local
```

Open [http://localhost:3000](http://localhost:3000), find `titanic_raw` in the asset graph, and click **Materialize**.

See [docs/guides/getting-started.md](docs/guides/getting-started.md) for a full walkthrough.

## Development

### Setup

Install all dependencies and set up pre-commit hooks:

```bash
just init
```

This runs `uv sync --all-groups --all-extras` and installs pre-commit hooks.

### Local

Run Dagster with your code changes (no Docker):

```bash
uv run dagster dev -m pluginlake.definitions
```

### Docker

Start the full dev environment with Docker Compose (Dagster + Postgres + FastAPI):

```bash
just dev-up
```

This starts:

| Container | Purpose |
|-----------|---------|
| postgres | Dagster metadata storage |
| dagster | All-in-one: webserver + daemon + code location |
| pluginlake | FastAPI service |

Source code is volume-mounted for hot reload. Stop with `just dev-down`.

### Quality checks

```bash
just test         # Run tests
just lint         # Run ruff + ty
just secure       # Security audit dependencies
just pre-commit   # Run all pre-commit hooks
just ci           # Run all checks (lint + test + secure)
```

## Production

Start the production deployment:

```bash
just up
```

This runs the full container architecture:

| Container | Image | Purpose |
|-----------|-------|---------|
| postgres | `dhi.io/postgres:17-alpine3.22` | Dagster metadata storage |
| dagster-webserver | `dagster-webserver.Dockerfile` | Web UI (port 3000) |
| dagster-daemon | `dagster-webserver.Dockerfile` | Schedules, sensors, run queue |
| dagster-code-server | `pluginlake.Dockerfile` | Serves asset definitions via gRPC (port 4000) |
| pluginlake | `pluginlake.Dockerfile` | FastAPI service |

Stop with `just down`.

## Using pluginlake as a package

Data stations with custom assets can import pluginlake and extend it. See [docs/guides/using-as-package.md](docs/guides/using-as-package.md).

## Stack

- **API:** FastAPI
- **Data:** DuckLake, Polars
- **Orchestration:** Dagster
- **Infrastructure:** Docker, Kubernetes, Traefik, PostgreSQL
- **UI:** Streamlit (FastAPI backend)

## Documentation

- [Getting started](docs/guides/getting-started.md) — Tutorial with the Titanic example
- [Using as a package](docs/guides/using-as-package.md) — Extend pluginlake in your own repo
- [Docker guide](docs/guides/docker.md) — Images, builds, and secrets management
- [Development guidelines](docs/develop-guidelines.md) — Coding standards and workflow
- [Architecture decisions](docs/decisions/README.md) — ADRs
