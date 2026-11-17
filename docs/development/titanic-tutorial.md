# Titanic tutorial

This tutorial walks you through running the included Titanic example to get familiar with pluginlake's asset pipeline.
It uses the development tooling for developers of the platform and of assets, so it runs without the login and the edge.
To run a complete node on your own machine, see [Getting started](../guides/getting-started.md).

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) installed
- Docker (for PostgreSQL)

## 1. Clone and install

```bash
git clone https://github.com/plugin-healthcare/pluginlake.git
cd pluginlake
just init
```

This installs all dependencies including Dagster, DuckDB, and Polars.

## 2. Start PostgreSQL

DuckLake stores its catalog metadata in PostgreSQL. Start the dev database:

```bash
just dev-up -d postgres
```

This starts a PostgreSQL 17 container on port 5432 using the Docker Compose dev stack.

## 3. Configure environment

Copy the example env file and adjust if needed:

```bash
cp .env.example .env
```

The defaults connect to the Docker Compose PostgreSQL. The `ensure_database` function in `setup.py` will automatically create the `ducklake` database on first run. If your PostgreSQL user differs from the default, update the values in `.env`.

## 4. Start the Dagster UI

Run the Titanic example:

```bash
just dev-local
```

Or directly:

```bash
uv run dagster dev -f examples/titanic.py
```

Open [http://localhost:3000](http://localhost:3000) in your browser. You should see the Dagster UI.

## 5. Explore the asset graph

Navigate to **Assets** in the left sidebar, then switch to the **Lineage** tab. You'll see three assets connected in a graph:

```text
              ┌──▶ titanic_survival_by_class
titanic_raw ──┤
              └──▶ titanic_survivors
```

- **titanic_raw** — Downloads the Titanic passenger dataset as a Polars DataFrame
- **titanic_survival_by_class** — Computes survival rate per passenger class (lazy read)
- **titanic_survivors** — Filters to survived passengers only, demonstrating filter pushdown (lazy read)

The arrows show dependencies: both downstream assets depend on `titanic_raw`.

## 6. Materialize an asset

Click on **titanic_raw** in the graph, then click **Materialize**. Dagster will:

1. Run the `titanic_raw` function
2. Download the Titanic CSV from GitHub
3. Store the resulting DataFrame to DuckLake via the IO manager

Once complete, you'll see a green checkmark on the asset.

## 7. Materialize the downstream assets

Materialize **titanic_survival_by_class** and **titanic_survivors** the same way.
Both receive the output of `titanic_raw` as a lazy frame.

## 8. Run the job

Instead of materializing assets one by one, go to **Jobs**, open **titanic_job** and click **Launch Run**.
This materializes all three assets in the correct order.

## 9. Explore the data

The assets are stored as tables in the DuckLake catalog, with the Parquet files in `.data/lakehouse/`.
Explore them with the DuckDB UI, marimo or the application of a project.

## 10. Understand the code

`examples/titanic.py` defines 3 assets with `@asset`, where function parameters declare the dependencies, 1 job with `define_asset_job`, and a `Definitions` object that registers them together with the DuckLake IO manager.
Assets that take a `pl.LazyFrame` get a lazy read, so Polars filters are pushed down to DuckDB.

## 11. Stop

Stop PostgreSQL when you're done.
The data stays in `.data/`, so the next start continues where you left off.

```bash
just dev-down
```

## Next steps

- **Add your own assets** and **use pluginlake as a package**: see the [using as package](../guides/using-as-package.md) guide.
- **Run a node**: see [Getting started](../guides/getting-started.md), and the [Docker guide](../guides/docker.md) for the background, settings and running options.
- **Explore the API**: see the [API overview](../reference/api.md) and the [interactive specification](../reference/api-specification.md).
