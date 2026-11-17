# Getting started with pluginlake

This tutorial walks you through running the included Titanic example to get familiar with pluginlake's asset pipeline. By the end you'll have materialized your first assets, inspected the DuckLake catalog, and queried the data.

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

## 9. Inspect the DuckLake catalog

Open a Python shell with `uv run python` and query the catalog:

```python
from pluginlake.core.ducklake.setup import setup_ducklake

conn = setup_ducklake()
conn.sql("SELECT table_schema, table_name FROM information_schema.tables WHERE table_catalog = 'ducklake'").show()
conn.sql("SELECT * FROM ducklake.main.titanic_survival_by_class").show()
```

The underlying Parquet files are in `.data/lakehouse/`.

## 10. Understand the code

`examples/titanic.py` defines 3 assets with `@asset`, where function parameters declare the dependencies, 1 job with `define_asset_job`, and a `Definitions` object that registers them together with the DuckLake IO manager.
Assets that take a `pl.LazyFrame` get a lazy read, so Polars filters are pushed down to DuckDB.

## 11. Clean up

Stop PostgreSQL when you're done, and optionally remove the DuckLake data files:

```bash
just dev-down
rm -rf .data/lakehouse/
```

## Next steps

- **Add your own assets** and **use pluginlake as a package**: see the [using as package](using-as-package.md) guide.
- **Run the full Docker stack**: see the [Docker guide](docker.md).
- **Explore the API**: see the [API overview](../reference/api.md) and the [interactive specification](../reference/api-specification.md).
