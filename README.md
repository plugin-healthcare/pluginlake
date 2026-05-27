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

Start the full dev environment with Docker Compose:

```bash
just dev-up           # With dashboard UI
just dev-up-headless  # Without dashboard
```

This mirrors the production architecture with source code mounted for hot reload:

| Container           | Purpose                                          |
| ------------------- | ------------------------------------------------ |
| postgres            | Dagster metadata + DuckLake catalog              |
| dagster-webserver   | Web UI + GraphQL API (port 3000)                 |
| dagster-daemon      | Schedules, sensors, run queue                    |
| dagster-code-server | Asset definitions via gRPC (port 4000)           |
| pluginlake          | FastAPI service (port 8000)                      |

Stop with `just dev-down`.

### Smoke test

Run an end-to-end integration test against the full stack:

```bash
just smoke-test-full
```

This starts an isolated stack with test fixtures (ephemeral volumes), runs `scripts/smoke_test.py` to validate the entire pipeline, then tears everything down. Safe for CI — leaves no state behind.

To run against an already-running dev stack:

```bash
just smoke-test
```

### Quality checks

```bash
just test         # Run tests
just lint         # Run ruff + ty
just secure       # Security audit dependencies
just pre-commit   # Run all pre-commit hooks
just ci           # Run all checks (lint + test + secure)
```

## Production

### Quick start (with CLI)

```bash
uv pip install -e .
pluginlake init
pluginlake up --instance ds-001
```

### Quick start (without CLI)

```bash
cp deploy/compose/.env.example deploy/compose/.env
# Edit .env — set POSTGRES_PASSWORD and paths
just up
```

See [docs/guides/deployment.md](docs/guides/deployment.md) for full setup instructions.

This runs the full container architecture:

| Container           | Image                           | Purpose                                       |
| ------------------- | ------------------------------- | --------------------------------------------- |
| postgres            | `dhi.io/postgres:17-alpine3.22` | Dagster metadata + DuckLake catalog            |
| dagster-webserver   | `dagster.Dockerfile`            | Web UI + GraphQL API (port 3000)               |
| dagster-daemon      | `dagster.Dockerfile`            | Schedules, sensors, run queue                  |
| dagster-code-server | `pluginlake.Dockerfile`         | Serves asset definitions via gRPC (port 4000)  |
| pluginlake          | `pluginlake.Dockerfile`         | FastAPI service                                |

Stop with `pluginlake down --instance ds-001` or `just down`.

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
- [Development guidelines](docs/development/develop-guidelines.md) — Coding standards and workflow
- [Architecture decisions](docs/decisions/README.md) — ADRs
