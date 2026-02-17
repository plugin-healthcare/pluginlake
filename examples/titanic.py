"""Titanic example — simple Dagster assets and job with Polars for verifying the pipeline setup."""

import polars as pl
from dagster import AssetSelection, Definitions, asset, define_asset_job

TITANIC_CSV_URL = (
    "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv"
)


@asset(description="Raw Titanic passenger data loaded from CSV into a Polars DataFrame.")
def titanic_raw() -> pl.DataFrame:
    """Download the Titanic CSV and return it as a Polars DataFrame."""
    return pl.read_csv(TITANIC_CSV_URL)


@asset(description="Titanic survival statistics grouped by passenger class.")
def titanic_survival_by_class(titanic_raw: pl.DataFrame) -> pl.DataFrame:
    """Compute survival rate per passenger class."""
    return titanic_raw.group_by("Pclass").agg(
        pl.col("Survived").mean().alias("survival_rate"),
        pl.col("Survived").count().alias("passenger_count"),
    )


titanic_job = define_asset_job(
    name="titanic_job",
    selection=AssetSelection.assets(titanic_raw, titanic_survival_by_class),
    description="Materialize all titanic assets.",
)

defs = Definitions(
    assets=[titanic_raw, titanic_survival_by_class],
    jobs=[titanic_job],
)
