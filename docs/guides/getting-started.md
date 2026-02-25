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

Navigate to **Assets** in the left sidebar. You'll see three assets connected in a graph:

```
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

Now click **titanic_survival_by_class** and materialize it. This asset receives the output of `titanic_raw` as a lazy frame and computes survival statistics grouped by class.

Do the same for **titanic_survivors** — it filters to survived passengers only, demonstrating how Polars filter predicates are pushed down to DuckDB.

## 8. Run the job

Instead of materializing assets one by one, you can run them together as a job.

Go to **Jobs** in the left sidebar. You'll see **titanic_job**. Click **Launch Run**. This materializes all three assets in the correct order.

## 9. Inspect the DuckLake catalog

After materializing assets, you can query the DuckLake catalog to see what was written. Open a Python shell:

```bash
uv run python
```

Then connect and explore:

```python
from pluginlake.core.ducklake.setup import setup_ducklake

conn = setup_ducklake()

# List all tables in the catalog
conn.sql("""
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_catalog = 'ducklake'
""").show()

# Preview the raw data
conn.sql("SELECT * FROM ducklake.main.titanic_raw LIMIT 5").show()

# Check the aggregated results
conn.sql("SELECT * FROM ducklake.main.titanic_survival_by_class").show()

# Check the filtered survivors
conn.sql("SELECT * FROM ducklake.main.titanic_survivors").show()
```

You can also inspect the underlying Parquet files DuckLake created:

```bash
ls -R .data/lakehouse/
```

Each table has its own directory with one or more `ducklake-{uuid}.parquet` files.

## 10. Understand the code

Open `examples/titanic.py` to see how it all fits together:

### Assets

Assets are Python functions decorated with `@asset`. The function name becomes the asset name. Dependencies are declared via function parameters:

```python
@asset
def titanic_raw() -> pl.DataFrame:
    """No dependencies — this is a root asset."""
    return pl.read_csv(TITANIC_CSV_URL)


@asset
def titanic_survival_by_class(titanic_raw: pl.LazyFrame) -> pl.DataFrame:
    """Depends on titanic_raw — receives a LazyFrame with pushdown support."""
    return titanic_raw.group_by("Pclass").agg(
        pl.col("Survived").mean().alias("survival_rate"),
        pl.col("Survived").count().alias("passenger_count"),
    ).collect()


@asset
def titanic_survivors(titanic_raw: pl.LazyFrame) -> pl.DataFrame:
    """Filters to survived passengers — filter is pushed down to DuckDB."""
    return (
        titanic_raw
        .filter(pl.col("Survived") == 1)
        .select("PassengerId", "Name", "Pclass", "Sex", "Age")
        .collect()
    )
```

### Jobs

Jobs group assets for execution. `define_asset_job` creates a job from an asset selection:

```python
titanic_job = define_asset_job(
    name="titanic_job",
    selection=AssetSelection.assets(
        titanic_raw, titanic_survival_by_class, titanic_survivors
    ),
)
```

### Definitions

The `Definitions` object registers everything with Dagster, including the DuckLake IO manager:

```python
defs = Definitions(
    assets=[titanic_raw, titanic_survival_by_class, titanic_survivors],
    jobs=[titanic_job],
    resources={"io_manager": ducklake_io_manager},
)
```

## 11. Clean up

Stop PostgreSQL when you're done:

```bash
just dev-down
```

To remove DuckLake data files:

```bash
rm -rf .data/lakehouse/
```

## Next steps

- **Add your own assets** — Create new `@asset` functions and add them to `Definitions`
- **Use pluginlake as a package** — See the [using as package](using-as-package.md) guide for building your own data station
- **Run the full Docker stack** — See the [Docker guide](docker.md) for running Dagster + PostgreSQL + pluginlake together
- **Explore Dagster** — Check the [Dagster docs](https://docs.dagster.io/) for schedules, sensors, resources, and more
