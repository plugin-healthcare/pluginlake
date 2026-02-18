# Getting started with pluginlake

This tutorial walks you through running the included Titanic example to get familiar with pluginlake's asset pipeline. By the end you'll have materialized your first assets and run a job in the Dagster UI.

## 1. Clone and install

```bash
git clone https://github.com/plugin-healthcare/pluginlake.git
cd pluginlake
just init
```

This installs all dependencies including Dagster.

## 2. Start the Dagster UI

Run the Titanic example:

```bash
uv run dagster dev -f examples/titanic.py
```

Open [http://localhost:3000](http://localhost:3000) in your browser. You should see the Dagster UI.

## 3. Explore the asset graph

Navigate to **Assets** in the left sidebar. You'll see two assets connected in a graph:

```
titanic_raw ──▶ titanic_survival_by_class
```

- **titanic_raw** — Downloads the Titanic passenger dataset as a Polars DataFrame
- **titanic_survival_by_class** — Computes survival rate per passenger class from `titanic_raw`

The arrow shows the dependency: `titanic_survival_by_class` depends on `titanic_raw`.

## 4. Materialize an asset

Click on **titanic_raw** in the graph, then click **Materialize**. Dagster will:

1. Run the `titanic_raw` function
2. Download the Titanic CSV from GitHub
3. Store the resulting DataFrame

Once complete, you'll see a green checkmark on the asset.

## 5. Materialize the downstream asset

Now click **titanic_survival_by_class** and materialize it. This asset receives the output of `titanic_raw` as its input and computes survival statistics grouped by class.

## 6. Run the job

Instead of materializing assets one by one, you can run them together as a job.

Go to **Jobs** in the left sidebar. You'll see **titanic_job**. Click **Launch Run**. This materializes both assets in the correct order.

## 7. Understand the code

Open `examples/titanic.py` to see how it all fits together:

### Assets

Assets are Python functions decorated with `@asset`. The function name becomes the asset name. Dependencies are declared via function parameters:

```python
@asset
def titanic_raw() -> pl.DataFrame:
    """No dependencies — this is a root asset."""
    return pl.read_csv(TITANIC_CSV_URL)


@asset
def titanic_survival_by_class(titanic_raw: pl.DataFrame) -> pl.DataFrame:
    """Depends on titanic_raw — receives its output as input."""
    return titanic_raw.group_by("Pclass").agg(
        pl.col("Survived").mean().alias("survival_rate"),
        pl.col("Survived").count().alias("passenger_count"),
    )
```

### Jobs

Jobs group assets for execution. `define_asset_job` creates a job from an asset selection:

```python
titanic_job = define_asset_job(
    name="titanic_job",
    selection=AssetSelection.assets(titanic_raw, titanic_survival_by_class),
)
```

### Definitions

The `Definitions` object registers everything with Dagster:

```python
defs = Definitions(
    assets=[titanic_raw, titanic_survival_by_class],
    jobs=[titanic_job],
)
```

## Next steps

- **Add your own assets** — Create new `@asset` functions and add them to `Definitions`
- **Use pluginlake as a package** — See the [using as package](using-as-package.md) guide for building your own data station
- **Explore Dagster** — Check the [Dagster docs](https://docs.dagster.io/) for schedules, sensors, resources, and more
