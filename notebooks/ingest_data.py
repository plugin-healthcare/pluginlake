"""Data Ingestion Demo

Upload Synthea OMOP CSV en FHIR NDJSON testdata naar de pluginlake API.
Download testdata automatisch, upload het, en poll Dagster totdat alle
getriggerde runs zijn afgerond.

Vereist `just dev-up` voor PostgreSQL, Dagster en FastAPI.
"""

import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Data Ingestion Demo

    Dit notebook demonstreert de volledige data-ingestie pipeline van het pluginlake platform aan de hand van synthetische Synthea testdata.

    Alle interactie met het platform verloopt via de **pluginlake REST API** (`http://localhost:8000/api/v1`).
    Wanneer je een bestand uploadt naar de API, gebeurt het volgende:

    1. De API valideert het bestand en slaat het tijdelijk op.
    2. Er wordt automatisch een **Dagster materialisatie-run** gestart die de data transformeert en wegschrijft naar **DuckLake** (een lakehouse met PostgreSQL als metadata-catalog en DuckDB als query-engine).
    3. De API retourneert een `dagster_run_id` waarmee je de voortgang kunt volgen.

    **Stappen in dit notebook:**

    1. **Pre-flight check**: controleer of alle services draaien
    2. **Testdata downloaden**: haal Synthea OMOP- en FHIR-datasets op
    3. **OMOP-ingestie**: upload CSV-bestanden naar de OMOP-endpoint
    4. **FHIR-ingestie**: upload NDJSON-bestanden naar de FHIR-endpoint
    5. **Runs monitoren**: volg de Dagster runs via de pluginlake API tot ze klaar zijn
    """)


@app.cell
def _():
    """Imports, constants, and helpers."""
    import os
    import re
    import time

    import httpx
    import marimo as mo
    from dotenv import load_dotenv

    from pluginlake.utils.testdata import (
        ensure_synthea1k,
        ensure_synthea_fhir_ndjson,
        find_repo_root,
    )

    load_dotenv()

    PROJECT_ROOT = find_repo_root()
    _port = os.getenv("PLUGINLAKE_SERVER_PORT", "8000")
    API_BASE = f"http://localhost:{_port}/api/v1"
    TIMEOUT = httpx.Timeout(timeout=120.0)

    def pascal_to_snake(name: str) -> str:
        return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()

    return (
        API_BASE,
        PROJECT_ROOT,
        TIMEOUT,
        ensure_synthea1k,
        ensure_synthea_fhir_ndjson,
        httpx,
        mo,
        pascal_to_snake,
        time,
    )


@app.cell
def _(mo):
    mo.md(r"""
    ## Pre-flight check

    Voordat we data kunnen uploaden, moet de dev-stack draaien.
    Start deze met `just dev-up`. Dit brengt de volgende services op:

    - **PostgreSQL**: database voor Dagster metadata en DuckLake catalog
    - **Dagster**: orchestrator die data-pipelines aanstuurt
    - **pluginlake API (FastAPI)**: REST API die als centraal toegangspunt dient

    De cel hieronder controleert of alle services bereikbaar zijn.
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
def _(PROJECT_ROOT, ensure_synthea1k, ensure_synthea_fhir_ndjson, mo):
    """Download Synthea OMOP and FHIR test datasets."""
    mo.md(r"""
    ## Testdata downloaden

    We gebruiken **Synthea** testdata: synthetisch gegenereerde patientgegevens in twee formaten:

    - **OMOP CDM** (CSV): het gestandaardiseerde datamodel voor observationeel onderzoek
    - **FHIR** (NDJSON): het HL7 FHIR uitwisselingsformaat, veelgebruikt in de zorg

    De datasets worden automatisch opgehaald van GitHub releases als ze nog niet lokaal aanwezig zijn.
    """)

    omop_dir = ensure_synthea1k(project_root=PROJECT_ROOT)
    fhir_dir = ensure_synthea_fhir_ndjson(project_root=PROJECT_ROOT)

    omop_files = sorted(omop_dir.glob("*.csv"))
    fhir_files = sorted(fhir_dir.glob("*.ndjson"))
    mo.md(
        f"OMOP: **{len(omop_files)}** CSV-bestanden in `{omop_dir.relative_to(PROJECT_ROOT)}`\n\n"
        f"FHIR: **{len(fhir_files)}** NDJSON-bestanden in `{fhir_dir.relative_to(PROJECT_ROOT)}`"
    )
    return fhir_files, omop_files


@app.cell
def _(mo):
    mo.md(r"""
    ## OMOP-ingestie

    Elk CSV-bestand wordt geupload naar het OMOP ingest-endpoint van de pluginlake API:

    ```
    POST /api/v1/omop/{tabel_naam}/csv
    ```

    De API ontvangt het bestand, valideert het tegen het OMOP CDM schema, en triggert een **Dagster materialisatie-run**.
    Dagster verwerkt de data en schrijft het resultaat weg naar DuckLake als Parquet-bestanden.
    De response bevat een `dagster_run_id` waarmee je de status van de verwerking kunt volgen.
    """)


@app.cell
def _(API_BASE, TIMEOUT, httpx, mo, omop_files):
    """Upload all Synthea CSVs to the OMOP ingest endpoint."""
    import polars as pl

    omop_results: list[dict] = []

    if not omop_files:
        mo.callout(mo.md("No CSV files found. Check the download step above."), kind="warn")
    else:
        for _csv_file in omop_files:
            _table_name = _csv_file.stem
            with _csv_file.open("rb") as _f:
                _resp = httpx.post(
                    f"{API_BASE}/omop/{_table_name}/csv",
                    files={"file": (_csv_file.name, _f, "text/csv")},
                    timeout=TIMEOUT,
                )
            omop_results.append(
                {
                    "table": _table_name,
                    "size_mb": round(_csv_file.stat().st_size / (1024 * 1024), 1),
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
    ## FHIR-ingestie

    FHIR-data wordt als NDJSON (newline-delimited JSON) geupload naar:

    ```
    POST /api/v1/fhir/{resource_type}/ndjson
    ```

    Niet alle FHIR resource types worden ondersteund. Pluginlake bevat **translators** die FHIR resources omzetten naar OMOP-tabellen (bijv. `Patient` naar `person`, `Condition` naar `condition_occurrence`).
    Bestanden met een niet-ondersteund resource type worden automatisch overgeslagen.

    Net als bij OMOP triggert elk upload-verzoek een Dagster run die de FHIR-data vertaalt en opslaat in DuckLake.
    """)


@app.cell
def _(API_BASE, TIMEOUT, fhir_files, httpx, mo, pascal_to_snake, pl):
    """Upload supported FHIR NDJSON files."""
    from pluginlake.fhir.translator_registry import FHIR_RESOURCE_TYPES

    supported = set(FHIR_RESOURCE_TYPES)
    fhir_results: list[dict] = []
    skipped: list[str] = []

    if not fhir_files:
        mo.callout(mo.md("No NDJSON files found. Check the download step above."), kind="warn")
    else:
        mapped = []
        for _f in fhir_files:
            _api_name = pascal_to_snake(_f.stem)
            if _api_name in supported:
                mapped.append((_f, _api_name))
            else:
                skipped.append(_f.stem)

        if skipped:
            mo.md(f"Skipping unsupported resource types: {', '.join(skipped)}")

        for _ndjson_file, _resource_type in mapped:
            with _ndjson_file.open("rb") as _fp:
                _resp = httpx.post(
                    f"{API_BASE}/fhir/{_resource_type}/ndjson",
                    files={"file": (_ndjson_file.name, _fp, "application/x-ndjson")},
                    timeout=TIMEOUT,
                )
            fhir_results.append(
                {
                    "resource_type": _resource_type,
                    "size_mb": round(_ndjson_file.stat().st_size / (1024 * 1024), 1),
                    "status": _resp.status_code,
                    "dagster_run_id": _resp.json().get("dagster_run_id"),
                    "message": _resp.json().get("message"),
                }
            )

        mo.md(f"Sent **{len(fhir_results)}** FHIR NDJSON files (skipped {len(skipped)})")
        mo.ui.table(pl.DataFrame(fhir_results))
    return (fhir_results,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Runs monitoren

    Na het uploaden willen we weten of alle verwerkingsruns succesvol zijn afgerond.
    We gebruiken hiervoor het pluginlake API endpoint per run:

    ```
    GET /api/v1/runs/{run_id}
    ```

    Dit endpoint retourneert de status van een specifieke Dagster run.
    We pollen dit endpoint elke paar seconden totdat alle getriggerde runs een eindstatus hebben bereikt (`SUCCESS`, `FAILURE`, of `CANCELED`).

    Alle communicatie met Dagster verloopt via de pluginlake API, zodat er later centraal autorisatie en authenticatie aan toegevoegd kan worden.
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
    """Poll the pluginlake API for individual run statuses until all complete."""
    TERMINAL_STATUSES = {"SUCCESS", "FAILURE", "CANCELED", "NOT_FOUND"}
    POLL_INTERVAL = 3

    all_results = omop_results + fhir_results
    run_ids = [r["dagster_run_id"] for r in all_results if r.get("dagster_run_id")]

    if not run_ids:
        mo.callout(mo.md("Er zijn geen Dagster runs gestart. Controleer de resultaten hierboven."), kind="warn")
    else:
        mo.md(f"**{len(run_ids)}** runs worden gemonitord via de pluginlake API...")

        while True:
            run_statuses = {}
            for _rid in run_ids:
                try:
                    _resp = httpx.get(f"{API_BASE}/runs/{_rid}", timeout=10.0)
                    _data = _resp.json() if _resp.is_success else {}
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
                mo.callout(mo.md(f"{table_md}\n\n**{len(failed)}** run(s) zijn niet geslaagd."), kind="warn")
            )
        else:
            mo.output.replace(mo.md(f"{table_md}\n\nAlle **{len(run_ids)}** runs zijn succesvol afgerond."))


@app.cell
def _(mo):
    mo.md(r"""
    ## Failed run triggeren (demo)

    Om te laten zien hoe het platform omgaat met fouten, uploaden we een ongeldig CSV-bestand naar het OMOP-endpoint.
    Het bestand bevat willekeurige kolommen die niet overeenkomen met het OMOP CDM schema.
    De API accepteert het bestand (het is immers een geldige CSV), maar de Dagster materialisatie-run zal falen tijdens de transformatiestap.

    Dit is nuttig om te testen of het monitoring-endpoint correct een `FAILURE`-status teruggeeft.
    """)


@app.cell
def _(API_BASE, TIMEOUT, httpx, mo, time):
    """Upload an invalid CSV to trigger a failed Dagster run."""
    import tempfile
    from pathlib import Path as _Path

    # Create a CSV with bogus columns that will fail OMOP schema validation in Dagster
    _invalid_csv = "foo,bar,baz\n1,2,3\n4,5,6\n"

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as _tmp:
        _tmp.write(_invalid_csv.encode())
        _tmp_path = _Path(_tmp.name)

    with _tmp_path.open("rb") as _f:
        _fail_resp = httpx.post(
            f"{API_BASE}/omop/person/csv",
            files={"file": ("person.csv", _f, "text/csv")},
            timeout=TIMEOUT,
        )

    _tmp_path.unlink(missing_ok=True)

    _HTTP_ERROR_THRESHOLD = 400
    if _fail_resp.status_code >= _HTTP_ERROR_THRESHOLD:
        mo.callout(
            mo.md(
                f"De API heeft het bestand direct geweigerd (HTTP {_fail_resp.status_code}). "
                "Probeer een ander table_name."
            ),
            kind="warn",
        )
    else:
        _fail_run_id = _fail_resp.json().get("dagster_run_id")
        mo.md(f"Ongeldig bestand geupload. Dagster run: `{_fail_run_id}`")

        # Poll until this run reaches a terminal status
        _TERMINAL = {"SUCCESS", "FAILURE", "CANCELED", "NOT_FOUND"}
        _status = "UNKNOWN"
        while _status not in _TERMINAL:
            time.sleep(3)
            try:
                _poll = httpx.get(f"{API_BASE}/runs/{_fail_run_id}", timeout=10.0)
                _status = _poll.json().get("status", "UNKNOWN") if _poll.is_success else "UNKNOWN"
            except httpx.HTTPError:
                _status = "UNREACHABLE"

        if _status == "FAILURE":
            mo.callout(
                mo.md(f"Run `{_fail_run_id[:12]}...` is gefaald zoals verwacht ({_status})."),
                kind="warn",
            )
        else:
            mo.callout(
                mo.md(f"Run `{_fail_run_id[:12]}...` eindigde met status **{_status}** (verwacht: FAILURE)."),
                kind="info",
            )


if __name__ == "__main__":
    app.run()
