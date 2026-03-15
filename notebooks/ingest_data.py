"""Data Ingestion

Upload OMOP CSV and FHIR NDJSON data to the pluginlake API. Polls Dagster
until all triggered runs have completed.

Requires `just dev-up` for PostgreSQL, Dagster, and FastAPI.
"""

import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Data Ingestion

    This notebook uploads data to the pluginlake API for processing.
    It covers both OMOP CSV and FHIR NDJSON ingestion, and polls Dagster
    until all triggered runs have completed.

    Sections:

    1. **Pre-flight check** — verify services are running
    2. **OMOP ingestion** — bulk upload Synthea CSV files
    3. **FHIR ingestion** — upload FHIR NDJSON bundles
    4. **Monitor runs** — poll Dagster until all runs finish
    """)


@app.cell
def _():
    """Imports, constants, and test data setup."""
    import io
    import time
    from pathlib import Path

    import httpx
    import marimo as mo

    from pluginlake.utils.testdata import find_repo_root

    PROJECT_ROOT = find_repo_root()
    from pluginlake.utils.testdata import ensure_synthea1k

    API_BASE = "http://localhost:8000/api/v1"
    DAGSTER_GRAPHQL = "http://localhost:3000/graphql"
    SYNTHEA_DIR = PROJECT_ROOT / "data" / "synthea" / "omop" / "synthea1k"
    FHIR_DIR = PROJECT_ROOT / "data" / "raw" / "fhir"

    ensure_synthea1k(project_root=PROJECT_ROOT)
    return (
        API_BASE,
        DAGSTER_GRAPHQL,
        FHIR_DIR,
        SYNTHEA_DIR,
        httpx,
        io,
        mo,
        time,
    )


@app.cell
def _(mo):
    mo.md(r"""
    ## Pre-flight Check

    The dev stack (`just dev-up`) must be running before we ingest data.
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
    ## OMOP Ingestion

    Upload every CSV in the Synthea 1K dataset to the OMOP ingest endpoint.
    Each file triggers a Dagster run that validates the data and writes it to DuckLake.
    """)


@app.cell
def _(API_BASE, SYNTHEA_DIR, httpx, mo):
    """Upload all Synthea CSVs to the OMOP ingest endpoint."""
    import polars as pl

    omop_results: list[dict] = []
    csv_files = sorted(SYNTHEA_DIR.glob("*.csv"))

    if not csv_files:
        mo.callout(mo.md(f"No CSV files found in `{SYNTHEA_DIR}`. Run `ensure_synthea1k()` first."), kind="warn")
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
    return omop_results, pl


@app.cell
def _(mo):
    mo.md(r"""
    ## FHIR Ingestion

    Upload FHIR NDJSON files from `data/raw/fhir/`. Each file should be named
    `{resource_type}.ndjson` (e.g. `patient.ndjson`, `condition.ndjson`).

    If no FHIR files exist yet, the cell below creates a small sample Patient bundle
    to demonstrate the endpoint.
    """)


@app.cell
def _(API_BASE, FHIR_DIR, httpx, io, mo, pl):
    """Upload FHIR NDJSON files, or create a sample if none exist."""
    FHIR_DIR.mkdir(parents=True, exist_ok=True)

    _SAMPLE_PATIENT_NDJSON = (
        '{"resourceType":"Patient","id":"example-1","gender":"male","birthDate":"1980-01-15","name":[{"family":"Smith","given":["John"]}]}\n'
        '{"resourceType":"Patient","id":"example-2","gender":"female","birthDate":"1992-06-22","name":[{"family":"Doe","given":["Jane"]}]}\n'
        '{"resourceType":"Patient","id":"example-3","gender":"male","birthDate":"1975-11-03","name":[{"family":"Johnson","given":["Robert"]}]}\n'
    )

    ndjson_files = sorted(FHIR_DIR.glob("*.ndjson"))
    fhir_results: list[dict] = []

    if ndjson_files:
        mo.md(f"Found **{len(ndjson_files)}** NDJSON files in `{FHIR_DIR}`")
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
    else:
        mo.md("No NDJSON files found — uploading a sample Patient bundle.")
        _resp = httpx.post(
            f"{API_BASE}/fhir/patient/ndjson",
            files={"file": ("patient.ndjson", io.BytesIO(_SAMPLE_PATIENT_NDJSON.encode()), "application/x-ndjson")},
            timeout=120.0,
        )
        fhir_results.append(
            {
                "resource_type": "patient",
                "status": _resp.status_code,
                "dagster_run_id": _resp.json().get("dagster_run_id"),
                "message": _resp.json().get("message"),
            }
        )

    mo.ui.table(pl.DataFrame(fhir_results))
    return (fhir_results,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Monitor Runs

    Poll Dagster for all triggered run IDs until they reach a terminal state.
    """)


@app.cell
def _(
    DAGSTER_GRAPHQL,
    fhir_results: list[dict],
    httpx,
    mo,
    omop_results: list[dict],
    time,
):
    """Poll Dagster until all runs complete."""
    TERMINAL_STATUSES = {"SUCCESS", "FAILURE", "CANCELED"}
    POLL_INTERVAL = 3

    _RUN_STATUS_QUERY = """
    query RunStatus($runId: ID!) {
      runOrError(runId: $runId) {
        __typename
        ... on Run { runId, status }
        ... on RunNotFoundError { message }
      }
    }
    """

    all_results = omop_results + fhir_results
    run_ids = [r["dagster_run_id"] for r in all_results if r.get("dagster_run_id")]

    if not run_ids:
        mo.callout(mo.md("No Dagster runs were triggered. Check the results above."), kind="warn")
    else:
        mo.md(f"Monitoring **{len(run_ids)}** Dagster runs...")

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


if __name__ == "__main__":
    app.run()
