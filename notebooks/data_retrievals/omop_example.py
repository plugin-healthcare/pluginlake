"""OMOP CDM Data Ingestion Example

This notebook demonstrates end-to-end OMOP data ingestion workflow:
1. Loading CSV files into Polars DataFrames
2. Validating against OMOP CDM schemas
3. Saving as Parquet files
4. Querying with DuckDB
5. Visualizing results
"""

import marimo

__generated_with = "0.19.11"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md("""
    # OMOP CDM Data Ingestion Workflow

    This notebook demonstrates the complete workflow for ingesting OMOP Common Data Model (CDM) data using the pluginlake OMOP module.

    ## Prerequisites

    - Synthea 1k dataset at `data/synthea/omop/synthea1k/`
    - OMOP module installed (`uv sync`)

    ## Workflow Steps

    1. Load CSV files
    2. Validate schemas
    3. Save as Parquet
    4. Query with DuckDB
    5. Visualize results
    """)


@app.cell
def _():
    from pathlib import Path

    import polars as pl

    from pluginlake.omop import (
        get_cohort,
        get_conditions_for_person,
        get_persons,
        load_omop_dataset,
        save_omop_table,
        validate_omop_table_schema,
    )

    return (
        Path,
        get_cohort,
        get_persons,
        load_omop_dataset,
        pl,
        save_omop_table,
        validate_omop_table_schema,
    )


@app.cell
def _(mo):
    mo.md("""
    ## Step 1: Load CSV Files
    """)


@app.cell
def _(Path, load_omop_dataset, mo):
    source_dir = Path("data/synthea/omop/synthea1k")

    if not source_dir.exists():
        mo.md(
            f"""
            ⚠️ **Warning**: Synthea data not found at `{source_dir}`

            Please download Synthea 1k dataset or adjust the path.
            """
        )
    else:
        tables = load_omop_dataset(source_dir, validate=False)

        mo.md(
            f"""
            ✅ **Loaded {len(tables)} OMOP tables** from `{source_dir}`

            Tables loaded:

            _Note: Validation disabled for Synthea data (contains date/datetime type differences)_
            """
        )
    return (tables,)


@app.cell
def _(mo, tables):
    table_summary = [{"Table": name, "Rows": len(df), "Columns": len(df.columns)} for name, df in tables.items()]

    mo.ui.table(table_summary)


@app.cell
def _(mo):
    mo.md("""
    ## Step 2: Validate Schemas
    """)


@app.cell
def _(mo, tables, validate_omop_table_schema):
    validation_results = []

    for table_name, df in tables.items():
        errors = validate_omop_table_schema(df, table_name)
        validation_results.append(
            {
                "Table": table_name,
                "Status": "✅ Valid" if not errors else f"❌ {len(errors)} errors",
                "Error Count": len(errors),
            }
        )

    mo.ui.table(validation_results)


@app.cell
def _(mo):
    mo.md("""
    ## Step 3: Save as Parquet

    Convert CSV files to Parquet format with ZSTD compression.
    """)


@app.cell
def _(Path, mo, save_omop_table, tables):
    output_dir = Path("data/omop/parquet/synthea1k")
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for table_name_2, table_df in tables.items():
        output_path = save_omop_table(table_df, table_name_2, output_dir=output_dir, overwrite=True)
        saved_files.append(
            {
                "Table": table_name_2,
                "Path": str(output_path),
                "Size": f"{output_path.stat().st_size / 1024:.1f} KB",
            }
        )

    mo.md(
        f"""
        ✅ **Saved {len(saved_files)} tables** to `{output_dir}`
        """
    )
    return output_dir, saved_files


@app.cell
def _(mo, saved_files):
    mo.ui.table(saved_files)


@app.cell
def _(mo):
    mo.md("""
    ## Step 4: Query with DuckDB
    """)


@app.cell
def _(get_persons, mo, output_dir):
    persons = get_persons(data_dir=output_dir, limit=10)

    mo.md(
        """
        ### Sample Persons

        First 10 persons from the dataset:
        """
    )
    return (persons,)


@app.cell
def _(mo, persons):
    mo.ui.table(persons.to_dicts())


@app.cell
def _(mo):
    mo.md("""
    ### Gender Distribution
    """)


@app.cell
def _(get_persons, output_dir, pl):
    all_persons = get_persons(data_dir=output_dir)

    gender_map = {8507: "Male", 8532: "Female", 8521: "Other", 8551: "Unknown"}

    gender_dist = (
        all_persons.group_by("gender_concept_id")
        .agg(pl.count("person_id").alias("count"))
        .with_columns(
            pl.col("gender_concept_id")
            .map_elements(lambda x: gender_map.get(x, "Unknown"), return_dtype=pl.Utf8)
            .alias("gender")
        )
        .select(["gender", "count"])
    )
    return all_persons, gender_dist


@app.cell
def _(gender_dist, mo):
    mo.ui.table(gender_dist.to_dicts())


@app.cell
def _(mo):
    mo.md("""
    ### Age Distribution
    """)


@app.cell
def _(all_persons, pl):
    from datetime import datetime

    current_year = datetime.now().year

    ages = (
        all_persons.with_columns((pl.lit(current_year) - pl.col("year_of_birth")).alias("age"))
        .select("age")
        .filter(pl.col("age") >= 0)
    )
    return (ages,)


@app.cell
def _(ages, mo, pl):
    age_bins = (
        ages.with_columns((pl.col("age") // 5 * 5).alias("age_range_start"))
        .with_columns(
            (pl.col("age_range_start").cast(pl.Utf8) + "-" + (pl.col("age_range_start") + 4).cast(pl.Utf8)).alias(
                "age_range"
            )
        )
        .group_by("age_range")
        .agg(pl.count("age").alias("count"))
        .sort("age_range")
    )

    mo.ui.table(age_bins.to_dicts())
    return (age_bins,)


@app.cell
def _(mo):
    mo.md("""
    ## Step 5: Cohort Selection
    """)


@app.cell
def _(get_cohort, mo, output_dir):
    diabetic_cohort = get_cohort(
        data_dir=output_dir,
        has_condition_concept_id=201826,
        min_age=40,
        max_age=70,
    )

    mo.md(
        f"""
        ### Diabetic Cohort (Age 40-70)

        Found **{len(diabetic_cohort)} persons** with Type 2 Diabetes between ages 40-70.
        """
    )
    return (diabetic_cohort,)


@app.cell
def _(diabetic_cohort, mo):
    if len(diabetic_cohort) > 0:
        mo.ui.table(diabetic_cohort.head(10).to_dicts())
    else:
        mo.md("No persons found matching cohort criteria.")


@app.cell
def _(mo):
    mo.md("""
    ## Summary

    This workflow demonstrated:

    1. ✅ **Loading** OMOP CSV files into Polars DataFrames
    2. ✅ **Validating** data against OMOP CDM v5.4 schemas
    3. ✅ **Saving** tables as compressed Parquet files (80-90% compression)
    4. ✅ **Querying** data using high-level DuckDB API
    5. ✅ **Analyzing** demographics and distributions
    6. ✅ **Selecting** cohorts with complex criteria

    ## Next Steps

    - Explore other query functions (`get_conditions_for_person`, `get_observations_for_person`, etc.)
    - Integrate with Dagster pipelines for automation
    - Use DuckLake for data lineage and versioning
    - Build custom analytics on top of OMOP data

    ## Resources

    - [OMOP Module Documentation](../docs/omop/README.md)
    - [ADR-002: OMOP Storage Architecture](../docs/decisions/adr-002-omop-storage-architecture.md)
    - [OMOP CDM v5.4 Specification](https://ohdsi.github.io/CommonDataModel/cdm54.html)
    """)


if __name__ == "__main__":
    app.run()
