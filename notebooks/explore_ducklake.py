import marimo

__generated_with = "0.19.10"
app = marimo.App(width="medium")


@app.cell
def _():
    """Connect to DuckLake catalog."""
    import marimo as mo

    from pluginlake.core.ducklake.setup import setup_ducklake

    conn = setup_ducklake()
    mo.md("## DuckLake Catalog Explorer\nConnected to DuckLake.")
    return conn, mo


@app.cell
def _(conn, mo):
    """List all schemas."""
    schemas = conn.sql("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE catalog_name = 'ducklake'
        ORDER BY schema_name
    """).pl()
    mo.md("### Schemas")
    return (schemas,)


@app.cell
def _(mo, schemas):
    mo.ui.table(schemas)


@app.cell
def _(conn, mo):
    """List all tables in the catalog."""
    tables = conn.sql("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_catalog = 'ducklake'
        ORDER BY table_schema, table_name
    """).pl()
    mo.md("### Tables")
    return (tables,)


@app.cell
def _(mo, tables):
    mo.ui.table(tables)


@app.cell
def _(conn, mo):
    """Snapshot history (version history of all writes)."""
    snapshots = conn.sql("SELECT * FROM ducklake_snapshots('ducklake')").pl()
    mo.md("### Snapshots (write history)")
    return (snapshots,)


@app.cell
def _(mo, snapshots):
    mo.ui.table(snapshots)


@app.cell
def _(conn, mo):
    """Table-level metadata."""
    table_info = conn.sql("SELECT * FROM ducklake_table_info('ducklake')").pl()
    mo.md("### Table info")
    return (table_info,)


@app.cell
def _(mo, table_info):
    mo.ui.table(table_info)


@app.cell
def _(conn, mo):
    """File-level info across all tables."""
    file_info = conn.sql("SELECT * FROM ducklake_list_files('ducklake')").pl()
    mo.md("### Backing Parquet files")
    return (file_info,)


@app.cell
def _(file_info, mo):
    mo.ui.table(file_info)


@app.cell
def _(conn, mo):
    """Preview titanic_raw."""
    raw = conn.sql("SELECT * FROM ducklake.main.titanic_raw LIMIT 10").pl()
    mo.md("### Preview: titanic_raw (first 10 rows)")
    return (raw,)


@app.cell
def _(mo, raw):
    mo.ui.table(raw)


@app.cell
def _(conn, mo):
    """Survival by class results."""
    survival = conn.sql("SELECT * FROM ducklake.main.titanic_survival_by_class").pl()
    mo.md("### titanic_survival_by_class")
    return (survival,)


@app.cell
def _(mo, survival):
    mo.ui.table(survival)


@app.cell
def _(conn, mo):
    """Survivors subset."""
    survivors = conn.sql("SELECT * FROM ducklake.main.titanic_survivors LIMIT 10").pl()
    mo.md("### Preview: titanic_survivors (first 10 rows)")
    return (survivors,)


@app.cell
def _(mo, survivors):
    mo.ui.table(survivors)


@app.cell
def _(conn, mo):
    """DuckLake configuration options."""
    options = conn.sql("SELECT * FROM ducklake_options('ducklake')").pl()
    mo.md("### DuckLake options")
    return (options,)


@app.cell
def _(mo, options):
    mo.ui.table(options)


if __name__ == "__main__":
    app.run()
