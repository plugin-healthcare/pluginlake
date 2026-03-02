import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Demo Increment 1: local datalake accessible through a REST API

    1. setup local pluginlake instance with the needed containers: `just dev-up`
    2. Download test omop data if not available locally
    3. start ingest pipeline by running this notebook
    4. check dagster UI to see the progress of the pipeline (http://localhost:3000)
    5. query ducklake directly to see the ingested data (see `explore_ducklake.py` for example on how to query ducklake)

    important:

    - check if ingest pipeline is following the suggested two step method from ADR 3 or 4 (ctrl+F for phase)
    - check if io_manager is used for ducklake in the asset for ingesting OMOP data.
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
            with open(csv_path, "rb") as fh:
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
def _(OMOP_DIR, ingest_csv_files):
    dataset_path = OMOP_DIR / "synthea1k"
    results = ingest_csv_files(dataset_path)
    results


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

    schemas
    mo.md("### Schemas")


if __name__ == "__main__":
    app.run()
