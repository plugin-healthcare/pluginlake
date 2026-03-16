"""DuckLake Catalog Explorer

Browse the DuckLake catalog: schemas, tables, snapshots, and table metadata.
Also materialises the Titanic demo dataset to demonstrate direct writes.

Requires `just dev-up` for PostgreSQL and DuckLake.
"""

import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # DuckLake Catalog Explorer

    This notebook connects directly to the DuckLake catalog and lets you:

    1. **Pre-flight check** - verify that the dev stack services are running
    2. **Titanic ingestion** - materialise the Titanic demo dataset into DuckLake
    3. **Catalog metadata** - browse schemas, tables, snapshots, and storage info
    4. **Data previews** - query the materialised Titanic tables
    """)


@app.cell
def _(mo):
    mo.md(r"""
    ## Pre-flight Service Check

    The dev stack (`just dev-up`) must be running before we can connect to DuckLake.
    The cell below probes each service and reports its status.
    """)


@app.cell
def _(mo):
    """Check connectivity to PostgreSQL, Dagster, and FastAPI."""
    from pluginlake.utils.devenv import check_dev_services

    statuses = check_dev_services()
    all_ok = all(s.ok for s in statuses)

    rows = "\n".join(f"| {'✅' if s.ok else '❌'} | {s.name} | `{s.url}` | {s.detail} |" for s in statuses)
    table = f"| | Service | URL | Status |\n|---|---|---|---|\n{rows}"

    if all_ok:
        mo.output.replace(mo.md(f"{table}\n\nAll services running."))
    else:
        mo.output.replace(
            mo.callout(
                mo.md(f"{table}\n\nRun `just dev-up` to start the dev stack."),
                kind="warn",
            )
        )


@app.cell
def _(mo):
    mo.md(r"""
    ## Connect to DuckLake

    Attach the DuckLake catalog using PostgreSQL as the metadata store and the local
    filesystem for parquet data. `OVERRIDE_DATA_PATH` remaps the container path
    (`/app/.data/lakehouse`) to the host-local equivalent.
    """)


@app.cell
def _():
    """Connect to the DuckLake catalog via PostgreSQL metadata + DuckDB engine."""
    from pathlib import Path

    import duckdb
    import marimo as mo

    from pluginlake.utils.testdata import find_repo_root

    project_root = find_repo_root()
    from pluginlake.core.config import DuckLakeSettings

    settings = DuckLakeSettings(pg_host="localhost")
    data_path = (project_root / settings.data_path).resolve()

    dl_conn = duckdb.connect()
    dl_conn.execute("INSTALL ducklake")
    dl_conn.execute("LOAD ducklake")
    dl_conn.execute(
        f"ATTACH 'ducklake:postgres:{settings.pg_connection_string}' "
        f"AS ducklake (DATA_PATH '{data_path}', OVERRIDE_DATA_PATH TRUE)"
    )
    mo.md("Connected to DuckLake.")
    return dl_conn, mo


@app.cell
def _(dl_conn, mo):
    """Download the Titanic CSV and materialise three tables into DuckLake."""
    mo.md(r"""
    ## Titanic Demo Assets

    Download the Titanic CSV and materialise three tables into DuckLake:
    raw passenger data, survival statistics by class, and a filtered survivors subset.
    This mirrors the `examples/titanic.py` Dagster assets but writes directly via DuckDB.
    """)

    import polars as pl

    TITANIC_CSV_URL = "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv"

    raw = pl.read_csv(TITANIC_CSV_URL)
    dl_conn.execute("CREATE SCHEMA IF NOT EXISTS ducklake.main")
    dl_conn.register("_data", raw)
    dl_conn.execute("CREATE OR REPLACE TABLE ducklake.main.titanic_raw AS SELECT * FROM _data")
    dl_conn.unregister("_data")

    survival = (
        raw.lazy()
        .group_by("Pclass")
        .agg(
            pl.col("Survived").mean().alias("survival_rate"),
            pl.col("Survived").count().alias("passenger_count"),
        )
        .collect()
    )
    dl_conn.register("_data", survival)
    dl_conn.execute("CREATE OR REPLACE TABLE ducklake.main.titanic_survival_by_class AS SELECT * FROM _data")
    dl_conn.unregister("_data")

    survivors = (
        raw.lazy().filter(pl.col("Survived") == 1).select("PassengerId", "Name", "Pclass", "Sex", "Age").collect()
    )
    dl_conn.register("_data", survivors)
    dl_conn.execute("CREATE OR REPLACE TABLE ducklake.main.titanic_survivors AS SELECT * FROM _data")
    dl_conn.unregister("_data")

    mo.md(
        f"Materialised **{len(raw)}** rows into `titanic_raw`, plus `titanic_survival_by_class` and `titanic_survivors`."
    )


@app.cell
def _(dl_conn, mo):
    mo.md(r"""
    ## Catalog Metadata

    Inspect the DuckLake catalog: available schemas, registered tables,
    snapshot (write) history, table-level storage info, and configuration options.
    """)


@app.cell
def _(dl_conn, mo):
    """List all schemas in the DuckLake catalog."""
    catalog_schemas = dl_conn.sql("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE catalog_name = 'ducklake'
        ORDER BY schema_name
    """).pl()
    mo.md("### Schemas")
    mo.ui.table(catalog_schemas)


@app.cell
def _(dl_conn, mo):
    """List all tables across all schemas in the catalog."""
    catalog_tables = dl_conn.sql("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_catalog = 'ducklake'
        ORDER BY table_schema, table_name
    """).pl()
    mo.md("### Tables")
    mo.ui.table(catalog_tables)


@app.cell
def _(dl_conn, mo):
    """Show the version history of all writes to the catalog."""
    catalog_snapshots = dl_conn.sql("SELECT * FROM ducklake_snapshots('ducklake')").pl()
    mo.md(
        "### Snapshots (write history)\n\nEach write creates a new snapshot, giving full version history of the catalog."
    )
    mo.ui.table(catalog_snapshots)


@app.cell
def _(dl_conn, mo):
    """Show row counts and storage metadata for each table."""
    catalog_table_info = dl_conn.sql("SELECT * FROM ducklake_table_info('ducklake')").pl()
    mo.md("### Table info\n\nRow counts and storage metadata for each table in the catalog.")
    mo.ui.table(catalog_table_info)


@app.cell
def _(dl_conn, mo):
    mo.md(r"""
    ## Titanic Data Previews

    Query the materialised Titanic tables to verify the data landed correctly.
    """)


@app.cell
def _(dl_conn, mo):
    """Preview the first 10 rows of the raw Titanic passenger data."""
    titanic_raw = dl_conn.sql("SELECT * FROM ducklake.main.titanic_raw LIMIT 10").pl()
    mo.md("### Preview: titanic_raw (first 10 rows)")
    mo.ui.table(titanic_raw)


@app.cell
def _(dl_conn, mo):
    """Show survival rate and passenger count grouped by class."""
    titanic_survival = dl_conn.sql("SELECT * FROM ducklake.main.titanic_survival_by_class").pl()
    mo.md("### titanic_survival_by_class\n\nSurvival rate and passenger count grouped by ticket class.")
    mo.ui.table(titanic_survival)


@app.cell
def _(dl_conn, mo):
    """Preview the first 10 survivors (passengers with Survived = 1)."""
    titanic_survivors = dl_conn.sql("SELECT * FROM ducklake.main.titanic_survivors LIMIT 10").pl()
    mo.md("### Preview: titanic_survivors (first 10 rows)\n\nFiltered to passengers who survived, showing key columns.")
    mo.ui.table(titanic_survivors)


@app.cell
def _(dl_conn, mo):
    mo.md(r"""
    ## DuckLake Configuration

    Current DuckLake extension options and their values.
    """)


@app.cell
def _(dl_conn, mo):
    """Show the current DuckLake extension configuration options."""
    ducklake_options = dl_conn.sql("SELECT * FROM ducklake_options('ducklake')").pl()
    mo.md("### DuckLake options")
    mo.ui.table(ducklake_options)


if __name__ == "__main__":
    app.run()
