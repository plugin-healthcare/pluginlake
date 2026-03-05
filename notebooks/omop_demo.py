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
    mo.md(r"""
    Start ingest pipeline by running this notebook via call to api endpoint with the path to the downloaded data as a parameter.
    """)


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import os
    from pathlib import Path

    import requests as _requests

    from pluginlake.utils.logger import get_logger

    logger = get_logger(__name__)

    # Local data directories
    DATA_DIR = Path(__file__).parent.parent / "data" / "synthea"
    OMOP_DIR = DATA_DIR / "omop"

    API_BASE_URL = os.getenv("PLUGINLAKE_API_URL", "http://localhost:8000")
    INGEST_ENDPOINT = os.getenv("PLUGINLAKE_INGEST_ENDPOINT", "/api/v1/ingest")

    def ingest_csv_files(data_path: Path, dataset: str = "omop") -> list[dict]:
        """Upload all CSV files from a directory to the ingest API.

        Streams each file as a multipart upload so large files do not
        need to be fully buffered on the client side.

        Args:
            data_path: Directory containing CSV files to upload.
            dataset: Target dataset name sent as a form field.

        Returns:
            List of parsed API response payloads, one per file.
        """
        if not data_path.exists():
            raise FileNotFoundError(f"OMOP path not found: {data_path}")

        url = f"{API_BASE_URL.rstrip('/')}{INGEST_ENDPOINT}"
        csv_files = sorted(data_path.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in {data_path}")

        results = []
        for csv_path in csv_files:
            logger.info("Uploading %s (%d bytes)", csv_path.name, csv_path.stat().st_size)
            with Path.open(csv_path, "rb") as fh:
                resp = _requests.post(
                    url,
                    files={"file": (csv_path.name, fh, "text/csv")},
                    data={"dataset": dataset},
                    timeout=300,
                )
            resp.raise_for_status()
            results.append(resp.json())
            logger.info("Ingested %s", csv_path.name)

        return results

    return OMOP_DIR, ingest_csv_files


@app.cell
def _(OMOP_DIR, ingest_csv_files, mo):
    dataset_path = OMOP_DIR / "synthea1k"
    results = ingest_csv_files(dataset_path)
    results  # noqa: B018
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
    mo.md(r"""
    Query ducklake directly to see the ingested data
    """)


@app.cell
def _(mo):
    """Connect to DuckLake catalog."""
    from pluginlake.core.ducklake.setup import setup_ducklake

    conn = setup_ducklake()
    mo.md("## DuckLake Catalog Explorer\nConnected to DuckLake.")
    return (conn,)


@app.cell
def _(conn, mo):
    """List all schemas."""
    schemas = conn.sql("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE catalog_name = 'ducklake'
        ORDER BY schema_name
    """).pl()
    schemas  # noqa: B018

    mo.md("### Schemas")
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
