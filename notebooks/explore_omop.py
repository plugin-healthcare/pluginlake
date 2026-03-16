"""OMOP Ingestion Demo

End-to-end demo of the pluginlake OMOP pipeline: pre-flight checks,
bulk CSV ingestion via the REST API, Dagster run polling, DuckLake
exploration, patient demographics, cohort selection, and single-table upload.

Requires `just dev-up` for PostgreSQL, Dagster, and FastAPI.
"""

import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Ingestion & Exploration Demo

    This notebook demonstrates the pluginlake ingestion pipeline end-to-end:

    1. **Pre-flight check** - verify that PostgreSQL, Dagster, and FastAPI are running
    2. **OMOP ingest** - upload Synthea-generated OMOP CSV files via the REST API
    3. **FHIR ingest** - upload Synthea FHIR NDJSON files via the REST API
    4. **Monitor runs** - poll the pluginlake API until all runs complete
    5. **Explore DuckLake** - query the ingested data directly through the DuckLake catalog
    6. **Demographics** - analyse gender and age distributions via DuckLake SQL
    7. **Cohort selection** - select patient cohorts by condition and age range
    """)


@app.cell
def _():
    """Set up imports, constants, and ensure test data is available."""
    import time
    from pathlib import Path

    import httpx
    import marimo as mo

    from pluginlake.utils.testdata import ensure_synthea1k

    API_BASE = "http://localhost:8000/api/v1"
    from pluginlake.utils.testdata import find_repo_root

    PROJECT_ROOT = find_repo_root()

    SYNTHEA_OMOP_DIR = PROJECT_ROOT / "data" / "synthea" / "omop" / "synthea1k"
    SYNTHEA_FHIR_DIR = PROJECT_ROOT / "data" / "synthea" / "fhir"

    ensure_synthea1k(project_root=PROJECT_ROOT)
    return (
        API_BASE,
        PROJECT_ROOT,
        SYNTHEA_FHIR_DIR,
        SYNTHEA_OMOP_DIR,
        httpx,
        mo,
        time,
    )


@app.cell
def _(mo):
    mo.md(r"""
    ## Pre-flight Service Check

    The dev stack (`just dev-up`) must be running before we can ingest data.
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
    ## OMOP Ingest

    Upload every CSV in the Synthea 1K dataset to the OMOP ingest endpoint (`POST /api/v1/omop/<table>/csv`).
    Each file triggers a Dagster materialisation run that validates the data against the OMOP CDM schema
    and persists it into DuckLake.
    """)


@app.cell
def _(API_BASE, SYNTHEA_OMOP_DIR, httpx, mo):
    """Upload all Synthea CSVs to the OMOP ingest endpoint."""
    import polars as pl

    omop_results: list[dict] = []
    csv_files = sorted(SYNTHEA_OMOP_DIR.glob("*.csv"))

    if not csv_files:
        mo.callout(mo.md(f"No CSV files found in `{SYNTHEA_OMOP_DIR}`. Run `ensure_synthea1k()` first."), kind="warn")
    else:
        for _csv_file in csv_files:
            _table_name = _csv_file.stem
            with _csv_file.open("rb") as _f:
                _resp = httpx.post(
                    f"{API_BASE}/omop/{_table_name}/csv",
                    files={"file": (_csv_file.name, _f, "text/csv")},
                    timeout=120.0,
                )
            omop_results.append(
                {
                    "table": _table_name,
                    "status": _resp.status_code,
                    "dagster_run_id": _resp.json().get("dagster_run_id"),
                    "message": _resp.json().get("message"),
                }
            )

        mo.md(f"Sent **{len(omop_results)}** OMOP CSV files")
        mo.ui.table(pl.DataFrame(omop_results))
    return (omop_results,)


@app.cell
def _(mo):
    mo.md(r"""
    ## FHIR Ingest

    Upload Synthea FHIR NDJSON files from `data/synthea/fhir/`.
    Run `notebooks/data_retrievals/retrieve_synthea.py` first to download the dataset.
    """)


@app.cell
def _(API_BASE, SYNTHEA_FHIR_DIR, httpx, mo):
    """Upload Synthea FHIR NDJSON files."""
    import polars as pl

    ndjson_files = sorted(SYNTHEA_FHIR_DIR.glob("*.ndjson"))
    fhir_results: list[dict] = []

    if not ndjson_files:
        mo.callout(
            mo.md(
                f"No NDJSON files found in `{SYNTHEA_FHIR_DIR}`.\n\n"
                "Run `notebooks/data_retrievals/retrieve_synthea.py` to download the Synthea FHIR dataset."
            ),
            kind="warn",
        )
    else:
        mo.md(f"Found **{len(ndjson_files)}** NDJSON files in `{SYNTHEA_FHIR_DIR}`")
        for _ndjson_file in ndjson_files:
            _resource_type = _ndjson_file.stem.lower()
            with _ndjson_file.open("rb") as _f:
                _resp = httpx.post(
                    f"{API_BASE}/fhir/{_resource_type}/ndjson",
                    files={"file": (_ndjson_file.name, _f, "application/x-ndjson")},
                    timeout=120.0,
                )
            fhir_results.append(
                {
                    "resource_type": _resource_type,
                    "status": _resp.status_code,
                    "dagster_run_id": _resp.json().get("dagster_run_id"),
                    "message": _resp.json().get("message"),
                }
            )

        mo.md(f"Sent **{len(fhir_results)}** FHIR NDJSON files")
        mo.ui.table(pl.DataFrame(fhir_results))
    return (fhir_results,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Monitor Runs

    Poll the pluginlake API (`GET /api/v1/runs`) until all triggered runs reach a terminal state.
    """)


@app.cell
def _(
    API_BASE,
    fhir_results: list[dict],
    httpx,
    mo,
    omop_results: list[dict],
    time,
):
    """Poll the pluginlake API for run status until all triggered runs complete."""
    TERMINAL_STATUSES = {"SUCCESS", "FAILURE", "CANCELED"}
    POLL_INTERVAL = 3

    all_results = omop_results + fhir_results
    run_ids = [r["dagster_run_id"] for r in all_results if r.get("dagster_run_id")]

    if not run_ids:
        mo.callout(mo.md("No Dagster runs were triggered. Check the results above."), kind="warn")
    else:
        mo.md(f"Monitoring **{len(run_ids)}** runs via pluginlake API...")

        while True:
            _runs_resp = httpx.get(f"{API_BASE}/runs", timeout=10.0)
            _all_runs = _runs_resp.json() if _runs_resp.is_success else []
            _status_lookup = {r["run_id"]: r["status"] for r in _all_runs if r.get("run_id")}

            run_statuses = {rid: _status_lookup.get(rid, "PENDING") for rid in run_ids}

            run_rows = "\n".join(f"| `{rid[:8]}…` | {status} |" for rid, status in run_statuses.items())
            table_md = f"| Run ID | Status |\n|---|---|\n{run_rows}"
            mo.output.replace(mo.md(table_md))

            if all(s in TERMINAL_STATUSES for s in run_statuses.values()):
                break
            time.sleep(POLL_INTERVAL)

        failed = [rid for rid, s in run_statuses.items() if s != "SUCCESS"]
        if failed:
            mo.output.replace(
                mo.callout(mo.md(f"{table_md}\n\n**{len(failed)}** run(s) did not succeed."), kind="warn")
            )
        else:
            mo.output.replace(mo.md(f"{table_md}\n\nAll **{len(run_ids)}** runs completed successfully."))


@app.cell
def _(mo):
    mo.md(r"""
    ## Explore DuckLake

    After ingestion, the data lives in DuckLake - a lakehouse layer that uses PostgreSQL as the
    metadata catalog and DuckDB as the query engine. The cells below connect directly to the
    catalog and let you browse tables, inspect write history (snapshots), and preview row-level data
    without going through the REST API.
    """)


@app.cell
def _(PROJECT_ROOT, mo):
    """Connect to the DuckLake catalog and list all tables."""
    import duckdb

    from pluginlake.core.config import DuckLakeSettings

    settings = DuckLakeSettings(pg_host="localhost")
    data_path = (PROJECT_ROOT / settings.data_path).resolve()
    conn = duckdb.connect()
    conn.execute("INSTALL ducklake")
    conn.execute("LOAD ducklake")
    conn.execute(
        f"ATTACH 'ducklake:postgres:{settings.pg_connection_string}' "
        f"AS ducklake (DATA_PATH '{data_path}', OVERRIDE_DATA_PATH TRUE)"
    )
    mo.md("Connected to DuckLake. Listing all tables in the catalog:")

    tables = conn.sql("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_catalog = 'ducklake'
        ORDER BY table_schema, table_name
    """).pl()
    mo.md("### Tables")

    mo.ui.table(tables)
    return (conn,)


@app.cell
def _(conn, mo):
    """Show snapshot (write) history for the catalog."""
    snapshots = conn.sql("SELECT * FROM ducklake_snapshots('ducklake')").pl()
    mo.md(
        "### Snapshots (write history)\n\nEach ingestion creates a new snapshot. This gives full version history of all writes to the catalog."
    )
    mo.ui.table(snapshots)


@app.cell
def _(conn, mo):
    """Show row counts and storage metadata for each table."""
    table_info = conn.sql("SELECT * FROM ducklake_table_info('ducklake')").pl()
    mo.md("### Table info\n\nRow counts and storage metadata for each table in the catalog.")
    mo.ui.table(table_info)


@app.cell
def _(conn, mo):
    """Preview the first 10 rows of the OMOP person table."""
    person = conn.sql("SELECT * FROM ducklake.omop.person LIMIT 10").pl()
    mo.md(
        "### Preview: omop.person (first 10 rows)\n\nSample rows from the OMOP `person` table to verify the data landed correctly."
    )
    mo.ui.table(person)


@app.cell
def _(conn, mo):
    """Load all persons from DuckLake for demographic analysis."""
    mo.md(r"""
    ## OMOP Demographics

    The cells below query the `ducklake.omop.person` table to analyse patient demographics.
    These will only return data after OMOP ingestion has been run (see `omop_demo.py`).
    """)

    persons = conn.sql("SELECT * FROM ducklake.omop.person").pl()
    mo.md(f"Loaded **{len(persons)}** persons.")


@app.cell
def _(conn, mo):
    """Query gender distribution from the OMOP person table."""
    mo.md("### Gender Distribution")

    gender_dist = conn.sql("""
        SELECT
            CASE gender_concept_id
                WHEN 8507 THEN 'Male'
                WHEN 8532 THEN 'Female'
                WHEN 8521 THEN 'Other'
                ELSE 'Unknown'
            END AS gender,
            COUNT(*) AS count
        FROM ducklake.omop.person
        GROUP BY gender_concept_id
        ORDER BY count DESC
    """).pl()
    mo.ui.table(gender_dist)


@app.cell
def _(conn, mo):
    """Compute age distribution in 5-year bins from year_of_birth."""
    mo.md(r"""
    ### Age Distribution

    Ages are computed from `year_of_birth` and grouped into 5-year bins.
    """)

    age_dist = conn.sql("""
        SELECT
            (EXTRACT(YEAR FROM CURRENT_DATE) - year_of_birth) / 5 * 5
                || '-'
                || (EXTRACT(YEAR FROM CURRENT_DATE) - year_of_birth) / 5 * 5 + 4
                AS age_range,
            COUNT(*) AS count
        FROM ducklake.omop.person
        WHERE EXTRACT(YEAR FROM CURRENT_DATE) - year_of_birth >= 0
        GROUP BY 1
        ORDER BY 1
    """).pl()
    mo.ui.table(age_dist)


@app.cell
def _(conn, mo):
    """Select a diabetic cohort by joining person and condition_occurrence."""
    mo.md(r"""
    ## Cohort Selection

    Select persons who have at least one `condition_occurrence` with a given concept ID,
    filtered by age range. This runs entirely in DuckLake - no intermediate parquet files needed.

    The example below selects persons with **Type 2 Diabetes** (concept 201826), aged 40-70.
    """)

    diabetic_cohort = conn.sql("""
        SELECT DISTINCT
            p.person_id,
            p.gender_concept_id,
            p.year_of_birth,
            EXTRACT(YEAR FROM CURRENT_DATE) - p.year_of_birth AS age
        FROM ducklake.omop.person p
        JOIN ducklake.omop.condition_occurrence co
            ON p.person_id = co.person_id
        WHERE co.condition_concept_id = 201826
            AND EXTRACT(YEAR FROM CURRENT_DATE) - p.year_of_birth BETWEEN 40 AND 70
        ORDER BY p.person_id
    """).pl()

    if len(diabetic_cohort) > 0:
        mo.md(f"### Diabetic Cohort (Age 40-70)\n\nFound **{len(diabetic_cohort)} persons**. First 10:")
        mo.ui.table(diabetic_cohort.head(10))
    else:
        mo.md("### Diabetic Cohort (Age 40-70)\n\nNo persons found matching cohort criteria.")


if __name__ == "__main__":
    app.run()
