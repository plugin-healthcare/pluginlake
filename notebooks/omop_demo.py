import marimo

__generated_with = "0.20.2"
app = marimo.App()


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


if __name__ == "__main__":
    app.run()
