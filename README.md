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

| Container  | Purpose                                        |
| ---------- | ---------------------------------------------- |
| postgres   | Dagster metadata storage                       |
| dagster    | All-in-one: webserver + daemon + code location |
| pluginlake | FastAPI service                                |

Source code is volume-mounted for hot reload. Stop with `just dev-down`.

### Lineage (Marquez)

Optionally, a station runs [Marquez](https://marquezproject.ai) as its OpenLineage receiver (ADR-007). Enable it in `pluginlake.toml`:

```toml
[station]
lineage = true
lineage_namespace = "ds-local-001"
```

Start the stack with `uv run pluginlake up -d` (`just dev-up` does not start the `lineage` profile). Materialize assets in Dagster ([http://localhost:3000](http://localhost:3000)); after each successful run the `openlineage_sensor` sends events to Marquez.

| What                       | Where                                                      |
| -------------------------- | ---------------------------------------------------------- |
| Marquez web UI             | [http://127.0.0.1:3001](http://127.0.0.1:3001) (loopback only) |
| Marquez API (via UI proxy) | `http://127.0.0.1:3001/api/v1/namespaces`                  |

In the UI, select your namespace to browse jobs and datasets (named after DuckLake tables, e.g. `ducklake.omop.person`). See [docs/guides/deploying-a-station.md](docs/guides/deploying-a-station.md#lineage-with-marquez-optional) for details.

### Quality checks

```bash
just test         # Run tests
just lint         # Run ruff + ty
just secure       # Security audit dependencies
just pre-commit   # Run all pre-commit hooks
just ci           # Run all checks (lint + test + secure)
```

## Production

A station runs the released, signed images without a checkout:

```bash
uv tool install pluginlake
pluginlake up -d     # in the station directory: pluginlake.toml, .env.production, secrets/
```

See [docs/guides/deploying-a-station.md](docs/guides/deploying-a-station.md) for the setup and [SECURITY.md](SECURITY.md) for the security measures and how to report a vulnerability.
`just up` starts the same production stack with images built from a checkout. It runs:

| Container           | Image                           | Purpose                                       |
| ------------------- | ------------------------------- | --------------------------------------------- |
| postgres            | `dhi.io/postgres:17-alpine3.24` | Dagster metadata storage                      |
| dagster-webserver   | `dagster-webserver`             | Web UI (port 3000, loopback)                  |
| dagster-daemon      | `dagster-webserver`             | Schedules, sensors, run queue                 |
| dagster-code-server | `api`                           | Serves asset definitions via gRPC (internal)  |
| pluginlake          | `api`                           | FastAPI service (port 8000)                   |

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
- [Development guidelines](docs/development/develop-guidelines.md) — Coding standards and workflow
- [Architecture decisions](docs/decisions/README.md) — ADRs
