r"""Titanic example — Dagster assets with DuckLake IO manager and lazy evaluation.

Demonstrates:
- Writing assets to DuckLake via the IO manager.
- Lazy reads: downstream assets receive a ``pl.LazyFrame`` with pushdown support.
- Collecting the lazy frame after transforms and returning a ``pl.DataFrame``
  for the IO manager to persist.

Run with::

    dagster dev -f examples/titanic.py

Then materialize the assets in the Dagster UI at http://localhost:3000.

To inspect the DuckLake catalog after materialization, open a DuckDB CLI::

    uv run python -c "
    import duckdb
    from pluginlake.core.ducklake.setup import setup_ducklake
    conn = setup_ducklake()
    conn.sql('SELECT table_schema, table_name FROM information_schema.tables WHERE table_catalog = \\'ducklake\\'').show()
    conn.sql('SELECT * FROM ducklake.main.titanic_raw LIMIT 5').show()
    conn.sql('SELECT * FROM ducklake.main.titanic_survival_by_class').show()
    "
"""

import polars as pl
from dagster import AssetSelection, Definitions, asset, define_asset_job

from pluginlake.core.ducklake.io_manager import ducklake_io_manager

TITANIC_CSV_URL = (
    "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv"
)


@asset(description="Raw Titanic passenger data loaded from CSV into a Polars DataFrame.")
def titanic_raw() -> pl.DataFrame:
    """Download the Titanic CSV and return it as a Polars DataFrame.

    This is a source asset: it fetches external data and returns a
    DataFrame. The DuckLake IO manager persists it to
    ``ducklake.main.titanic_raw``.
    """
    return pl.read_csv(TITANIC_CSV_URL)


@asset(description="Titanic survival statistics grouped by passenger class (lazy read).")
def titanic_survival_by_class(titanic_raw: pl.LazyFrame) -> pl.DataFrame:
    """Compute survival rate per passenger class.

    Receives a ``pl.LazyFrame`` from the IO manager. Polars pushes
    the ``group_by`` and ``agg`` down to DuckDB at collect time,
    only materializing the small aggregated result.
    """
    result = titanic_raw.group_by("Pclass").agg(
        pl.col("Survived").mean().alias("survival_rate"),
        pl.col("Survived").count().alias("passenger_count"),
    ).collect()
    assert isinstance(result, pl.DataFrame)
    return result


@asset(description="Filtered subset: only passengers who survived (lazy read + filter pushdown).")
def titanic_survivors(titanic_raw: pl.LazyFrame) -> pl.DataFrame:
    """Filter to survived passengers only.

    Demonstrates filter pushdown: the ``pl.col('Survived') == 1``
    predicate is translated to a SQL WHERE clause by DuckDB's Polars
    IO plugin, enabling DuckLake file pruning on large tables.
    """
    result = (
        titanic_raw
        .filter(pl.col("Survived") == 1)
        .select("PassengerId", "Name", "Pclass", "Sex", "Age")
        .collect()
    )
    assert isinstance(result, pl.DataFrame)
    return result


titanic_job = define_asset_job(
    name="titanic_job",
    selection=AssetSelection.assets(
        titanic_raw, titanic_survival_by_class, titanic_survivors
    ),
    description="Materialize all titanic assets.",
)

defs = Definitions(
    assets=[titanic_raw, titanic_survival_by_class, titanic_survivors],
    jobs=[titanic_job],
    resources={"io_manager": ducklake_io_manager},
)
