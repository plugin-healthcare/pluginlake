import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import io

    import httpx
    import marimo as mo

    BASE_URL = "http://localhost:8000/api/v1/omop"
    return BASE_URL, httpx, io, mo


@app.cell
def _(mo):
    mo.md(r"""
    # Demo Increment 1: local datalake accessible through a REST API

    1. Set up local pluginlake instance with the needed containers: `just dev-up`
    2. Download test OMOP data if not available locally
    3. Start the ingest pipeline by running this notebook
    4. Check the Dagster UI to see the progress of the pipeline (http://localhost:3000)
    5. Query DuckLake directly to see the ingested data (see `explore_ducklake.py`)
    """)


@app.cell
def _(mo):
    mo.md("## Ingest all Synthea CSVs")


@app.cell
def _(BASE_URL, httpx, mo):
    from pathlib import Path

    SYNTHEA_DIR = Path("../data/synthea/omop/synthea1k")

    results = []
    for csv_file in sorted(SYNTHEA_DIR.glob("*.csv")):
        table_name = csv_file.stem
        with csv_file.open("rb") as f:
            resp = httpx.post(
                f"{BASE_URL}/{table_name}/csv",
                files={"file": (csv_file.name, f, "text/csv")},
                timeout=120.0,
            )
        results.append(
            {
                "table": table_name,
                "status": resp.status_code,
                "dagster_run_id": resp.json().get("dagster_run_id"),
                "message": resp.json().get("message"),
            }
        )

    mo.md(f"Sent {len(results)} files")
    return (results,)


@app.cell
def _(mo, results):
    import polars as pl

    mo.ui.table(pl.DataFrame(results))


@app.cell
def _(mo):
    mo.md("## CSV Upload (`observation_period`)")


@app.cell
def _(BASE_URL, httpx, io, mo):
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
    return (csv_result,)


@app.cell
def _(csv_result, mo):
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
