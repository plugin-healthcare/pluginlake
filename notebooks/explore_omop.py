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
    # OMOP Ingestion Demo

    This notebook demonstrates the pluginlake ingestion pipeline end-to-end:

    1. **Pre-flight check** - verify that PostgreSQL, Dagster, and FastAPI are running
    2. **Bulk ingest** - upload Synthea-generated OMOP CSV files via the REST API
    3. **Explore DuckLake** - query the ingested data directly through the DuckLake catalog
    4. **Demographics** - analyse gender and age distributions via DuckLake SQL
    5. **Cohort selection** - select patient cohorts by condition and age range
    6. **Single-table upload** - upload a small CSV inline to show the single-file API
    """)


@app.cell
def _():
    """Set up imports, constants, and ensure test data is available."""
    import io
    from pathlib import Path

    import httpx
    import marimo as mo

    from pluginlake.utils.testdata import ensure_synthea1k

    BASE_URL = "http://localhost:8000/api/v1/omop"
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    SYNTHEA_DIR = PROJECT_ROOT / "data" / "synthea" / "omop" / "synthea1k"
    ensure_synthea1k(project_root=PROJECT_ROOT)
    return BASE_URL, PROJECT_ROOT, SYNTHEA_DIR, httpx, io, mo


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
    ## Bulk Ingest

    Upload every CSV in the Synthea 1K dataset to the OMOP ingest endpoint (`POST /api/v1/omop/<table>/csv`).
    Each file triggers a Dagster materialisation run that validates the data against the OMOP CDM schema
    and persists it into DuckLake. The table below shows the HTTP response for each file.
    """)


@app.cell
def _(BASE_URL, SYNTHEA_DIR, httpx, mo):
    """Upload all Synthea CSVs to the OMOP ingest endpoint."""
    import polars as pl

    results = []
    for _csv_file in sorted(SYNTHEA_DIR.glob("*.csv")):
        _table_name = _csv_file.stem
        with _csv_file.open("rb") as _f:
            _resp = httpx.post(
                f"{BASE_URL}/{_table_name}/csv",
                files={"file": (_csv_file.name, _f, "text/csv")},
                timeout=120.0,
            )
        results.append(
            {
                "table": _table_name,
                "status": _resp.status_code,
                "dagster_run_id": _resp.json().get("dagster_run_id"),
                "message": _resp.json().get("message"),
            }
        )

    mo.md(f"Sent {len(results)} files")

    mo.ui.table(pl.DataFrame(results))
    return (results,)


@app.cell
def _(httpx, mo, results):
    """Poll Dagster GraphQL for run status until all runs reach a terminal state."""
    import time

    DAGSTER_GRAPHQL = "http://localhost:3000/graphql"
    TERMINAL_STATUSES = {"SUCCESS", "FAILURE", "CANCELED"}
    POLL_INTERVAL = 3

    _RUN_STATUS_QUERY = """
    query RunStatus($runId: ID!) {
      runOrError(runId: $runId) {
        __typename
        ... on Run {
          runId
          status
        }
        ... on RunNotFoundError {
          message
        }
      }
    }
    """

    run_ids = [r["dagster_run_id"] for r in results if r.get("dagster_run_id")]

    if not run_ids:
        mo.callout(mo.md("No Dagster runs were triggered. Check the ingest results above."), kind="warn")
    else:
        while True:
            run_statuses = {}
            for _rid in run_ids:
                try:
                    _resp = httpx.post(
                        DAGSTER_GRAPHQL,
                        json={"query": _RUN_STATUS_QUERY, "variables": {"runId": _rid}},
                        timeout=10.0,
                    )
                    _data = _resp.json().get("data", {}).get("runOrError", {})
                    run_statuses[_rid] = _data.get("status", "UNKNOWN")
                except httpx.HTTPError:
                    run_statuses[_rid] = "UNREACHABLE"

            run_rows = "\n".join(f"| `{rid[:8]}...` | {status} |" for rid, status in run_statuses.items())
            table_md = f"| Run ID | Status |\n|---|---|\n{run_rows}"
            mo.output.replace(mo.md(f"## Waiting for Dagster runs\n\n{table_md}"))

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

    ingestion_complete = True
    return (ingestion_complete,)


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
def _(PROJECT_ROOT, ingestion_complete, mo):
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


@app.cell
def _(mo):
    mo.md(r"""
    ## Single-Table Upload

    Besides bulk ingestion you can also upload individual tables. Below we POST a small inline
    CSV (`observation_period`) to demonstrate the single-file endpoint. The response includes the
    Dagster run ID so you can track the materialisation in the Dagster UI at http://localhost:3000.
    """)


@app.cell
def _(BASE_URL, httpx, io, mo):
    """Upload a small inline CSV to demonstrate the single-file ingest endpoint."""
    _csv = """\
    observation_period_id,person_id,observation_period_start_date,observation_period_end_date,period_type_concept_id
    1,1,2020-01-01,2023-12-31,44814724
    2,2,2019-06-01,2023-12-31,44814724
    3,3,2021-03-15,2023-12-31,44814724
    """

    _resp = httpx.post(
        f"{BASE_URL}/observation_period/csv",
        files={"file": ("observation_period.csv", io.BytesIO(_csv.encode()), "text/csv")},
    )
    csv_result = _resp.json()
    mo.md(f"**HTTP {_resp.status_code}**")

    mo.md(rf"""
    | field | value |
    |---|---|
    | status | `{csv_result.get("status")}` |
    | file\_path | `{csv_result.get("file_path")}` |
    | size\_bytes | {csv_result.get("size_bytes")} |
    | dagster\_run\_id | `{csv_result.get("dagster_run_id")}` |
    | message | {csv_result.get("message")} |

    > If `dagster_run_id` is `None`, Dagster was unreachable — the CSV is still stored and can be
    > re-triggered manually. Check http://localhost:3000 to confirm the run.
    """)


if __name__ == "__main__":
    app.run()
