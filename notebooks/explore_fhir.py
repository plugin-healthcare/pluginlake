"""Explore FHIR Data

Interactive exploration of FHIR NDJSON data: loading, inspecting resource
structure, querying raw resources with DuckDB, and understanding the
FHIR-to-OMOP translation pipeline.

Uses Synthea-generated FHIR data downloaded from the pluginlake-testdata
repository. No dev stack required — all queries run locally via DuckDB.
"""

import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Explore FHIR Data

    This notebook walks through the FHIR data pipeline in pluginlake:

    1. **Download** — fetch Synthea FHIR NDJSON test data
    2. **Load & inspect** — use the FHIR loader to read NDJSON files
    3. **Resource structure** — examine the JSON schema of each resource type
    4. **Query with DuckDB** — run analytical queries directly over raw FHIR JSON
    5. **FHIR-to-OMOP mapping** — preview how resources translate to OMOP CDM tables
    """)


@app.cell
def _():
    from pathlib import Path

    import marimo as mo
    import polars as pl

    from pluginlake.utils.testdata import find_repo_root

    PROJECT_ROOT = find_repo_root()
    from pluginlake.fhir.loader import load_fhir_dataset, load_fhir_ndjson
    from pluginlake.fhir.translator_registry import (
        FHIR_RESOURCE_TYPES,
        FHIR_TO_OMOP_TABLE,
        get_translator,
    )
    from pluginlake.utils.testdata import ensure_synthea_fhir_ndjson

    return (
        FHIR_RESOURCE_TYPES,
        FHIR_TO_OMOP_TABLE,
        PROJECT_ROOT,
        Path,
        ensure_synthea_fhir_ndjson,
        get_translator,
        load_fhir_dataset,
        load_fhir_ndjson,
        mo,
        pl,
    )


@app.cell
def _(PROJECT_ROOT, ensure_synthea_fhir_ndjson, mo):
    mo.md(r"""
    ## Download FHIR NDJSON Data

    The Synthea FHIR NDJSON files are downloaded automatically from the
    `pluginlake-testdata` repository if not already present locally.
    Each file contains one resource type (Patient, Condition, etc.) with
    one JSON object per line.
    """)

    ndjson_dir = ensure_synthea_fhir_ndjson(project_root=PROJECT_ROOT)
    mo.md(f"FHIR NDJSON data ready at `{ndjson_dir}`")
    return (ndjson_dir,)


@app.cell
def _(mo, ndjson_dir, pl):
    mo.md(r"""
    ## Load & Inspect

    List all available NDJSON files with their sizes and line counts.
    """)

    ndjson_files = sorted(ndjson_dir.glob("*.ndjson"))
    file_info = []
    for f in ndjson_files:
        line_count = sum(1 for line in f.open("rb") if line.strip())
        file_info.append(
            {
                "file": f.name,
                "resource_type": f.stem,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "resources": line_count,
            }
        )

    file_df = pl.DataFrame(file_info)
    mo.md(f"Found **{len(ndjson_files)}** NDJSON files with **{file_df['resources'].sum():,}** total resources:")
    mo.ui.table(file_df)
    return file_df, ndjson_dir, ndjson_files


@app.cell
def _(load_fhir_dataset, mo, ndjson_dir):
    mo.md(r"""
    ## Load with FHIR Loader

    `load_fhir_dataset()` reads all NDJSON files into single-column Polars DataFrames
    (column `json_data`). This is the same loader used by the Dagster FHIR assets
    during ingestion.
    """)

    fhir_tables = load_fhir_dataset(data_dir=ndjson_dir)
    summary = {rtype: len(df) for rtype, df in sorted(fhir_tables.items())}
    mo.md("Loaded resource types: " + ", ".join(f"**{rtype}** ({count:,})" for rtype, count in summary.items()))
    return (fhir_tables,)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## Resource Structure

    Parse the first resource from each type to see what fields FHIR provides.
    This helps understand what data is available before translation to OMOP.
    """)


@app.cell
def _(fhir_tables, mo, pl):
    import orjson

    structure_rows = []
    for rtype, df in sorted(fhir_tables.items()):
        first_json = orjson.loads(df["json_data"][0])
        top_keys = sorted(first_json.keys())
        structure_rows.append(
            {
                "resource_type": rtype,
                "fields": ", ".join(top_keys),
                "field_count": len(top_keys),
            }
        )

    mo.md("### Top-level fields per resource type")
    mo.ui.table(pl.DataFrame(structure_rows))
    return (orjson,)


@app.cell
def _(fhir_tables, mo, orjson):
    if "patient" in fhir_tables:
        sample = orjson.loads(fhir_tables["patient"]["json_data"][0])
        mo.md(
            "### Sample Patient resource\n\n"
            "```json\n" + orjson.dumps(sample, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode() + "\n```"
        )
    else:
        mo.md("_No Patient resources available._")


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## Query Raw FHIR with DuckDB

    DuckDB can query JSON strings directly using `json_extract` / `json_extract_string`.
    This lets us run analytical queries over raw FHIR data without any transformation step.
    """)


@app.cell
def _(fhir_tables, mo):
    import duckdb

    conn = duckdb.connect()

    for rtype, df in fhir_tables.items():
        conn.register(f"fhir_{rtype}", df.to_arrow())

    mo.md(f"Registered **{len(fhir_tables)}** FHIR tables in DuckDB.")
    return (conn,)


@app.cell
def _(conn, mo):
    if "patient" in [t[0] for t in conn.execute("SHOW TABLES").fetchall()]:
        mo.md("### Patient Demographics (from raw FHIR JSON)")

        patient_demo = conn.sql("""
            SELECT
                json_extract_string(json_data, '$.gender') AS gender,
                COUNT(*) AS count
            FROM fhir_patient
            GROUP BY gender
            ORDER BY count DESC
        """).pl()
        mo.ui.table(patient_demo)


@app.cell
def _(conn, mo):
    if "fhir_patient" in [f"fhir_{t[0]}" for t in conn.execute("SHOW TABLES").fetchall()]:
        mo.md("### Birth Year Distribution")

        birth_years = conn.sql("""
            SELECT
                json_extract_string(json_data, '$.birthDate')[:4] AS birth_year,
                COUNT(*) AS count
            FROM fhir_patient
            WHERE json_extract_string(json_data, '$.birthDate') IS NOT NULL
            GROUP BY birth_year
            ORDER BY birth_year
        """).pl()
        mo.ui.table(birth_years)


@app.cell
def _(conn, mo):
    if "fhir_condition" in [f"fhir_{t[0]}" for t in conn.execute("SHOW TABLES").fetchall()]:
        mo.md("### Top 20 Conditions (by SNOMED code)")

        top_conditions = conn.sql("""
            SELECT
                json_extract_string(json_data, '$.code.coding[0].code') AS snomed_code,
                json_extract_string(json_data, '$.code.coding[0].display') AS display,
                COUNT(*) AS count
            FROM fhir_condition
            WHERE json_extract_string(json_data, '$.code.coding[0].code') IS NOT NULL
            GROUP BY snomed_code, display
            ORDER BY count DESC
            LIMIT 20
        """).pl()
        mo.ui.table(top_conditions)


@app.cell
def _(conn, mo):
    if "fhir_observation" in [f"fhir_{t[0]}" for t in conn.execute("SHOW TABLES").fetchall()]:
        mo.md("### Top 20 Observation Types (by LOINC code)")

        top_obs = conn.sql("""
            SELECT
                json_extract_string(json_data, '$.code.coding[0].code') AS loinc_code,
                json_extract_string(json_data, '$.code.coding[0].display') AS display,
                COUNT(*) AS count
            FROM fhir_observation
            WHERE json_extract_string(json_data, '$.code.coding[0].code') IS NOT NULL
            GROUP BY loinc_code, display
            ORDER BY count DESC
            LIMIT 20
        """).pl()
        mo.ui.table(top_obs)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## FHIR-to-OMOP Translation Mapping

    pluginlake uses `plugin-rosetta` translators to convert FHIR resources
    into OMOP CDM tables. The mapping below shows which FHIR resource types
    feed into which OMOP tables.
    """)


@app.cell
def _(FHIR_TO_OMOP_TABLE, mo, pl):
    mapping_df = pl.DataFrame(
        [{"fhir_resource": fhir, "omop_table": omop} for fhir, omop in sorted(FHIR_TO_OMOP_TABLE.items())]
    )

    mo.md("### Resource Type Mapping")
    mo.ui.table(mapping_df)


@app.cell
def _(fhir_tables, get_translator, mo, orjson, pl):
    mo.md(r"""
    ### Translation Preview

    Translate the first resource of each type to see what the OMOP output looks like.
    """)

    preview_rows = []
    for rtype in sorted(fhir_tables):
        try:
            translator = get_translator(rtype)
        except ValueError:
            continue

        first_resource = orjson.loads(fhir_tables[rtype]["json_data"][0])
        try:
            result = translator.translate(first_resource)
            preview_rows.append(
                {
                    "fhir_resource": rtype,
                    "omop_fields": ", ".join(sorted(result.keys()))
                    if isinstance(result, dict)
                    else str(type(result).__name__),
                    "status": "OK",
                }
            )
        except (ValueError, KeyError, TypeError) as exc:
            preview_rows.append(
                {
                    "fhir_resource": rtype,
                    "omop_fields": "",
                    "status": f"Error: {exc}",
                }
            )

    mo.ui.table(pl.DataFrame(preview_rows))


if __name__ == "__main__":
    app.run()
