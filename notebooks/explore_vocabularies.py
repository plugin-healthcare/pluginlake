"""Explore OMOP Vocabularies

Interactive exploration of the OMOP vocabulary query and validation APIs.
Connects to the DuckLake catalog to browse vocabularies, look up concepts,
search by name, navigate the concept hierarchy, map source codes, and
validate concept IDs.

Requires `just dev-up` and vocabulary data loaded into DuckLake.
"""

import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Explore OMOP Vocabularies

    This notebook walks through the vocabulary functionality in `pluginlake.omop`:

    1. **Connect** to the DuckLake catalog
    2. **Browse vocabularies** — list all loaded vocabularies and their metadata
    3. **Look up concepts** — retrieve a concept by ID
    4. **Search concepts** — find concepts by name with domain/vocabulary filters
    5. **Navigate hierarchy** — explore ancestors and descendants of a concept
    6. **Map source codes** — translate ICD-10 / local codes to standard OMOP concepts
    7. **Validate concept IDs** — check whether concept IDs are valid, standard, and in the right domain
    """)


@app.cell
def _():
    from pathlib import Path

    import marimo as mo

    from pluginlake.omop.loader import load_vocabulary_dataset
    from pluginlake.omop.vocabulary_queries import (
        get_concept,
        get_concept_ancestors,
        get_concept_descendants,
        get_vocabulary_info,
        map_source_code,
        search_concepts,
    )
    from pluginlake.omop.vocabulary_validation import (
        validate_concept_ids,
    )
    from pluginlake.utils.testdata import ensure_omop_vocabularies

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    return (
        PROJECT_ROOT,
        ensure_omop_vocabularies,
        load_vocabulary_dataset,
        get_concept,
        get_concept_ancestors,
        get_concept_descendants,
        get_vocabulary_info,
        map_source_code,
        mo,
        search_concepts,
        validate_concept_ids,
    )


@app.cell
def _(PROJECT_ROOT, ensure_omop_vocabularies, mo):
    mo.md(r"""
    ## Download Vocabulary Data

    The OMOP vocabulary CSV files (CONCEPT, VOCABULARY, DOMAIN, etc.) are downloaded
    automatically from the pluginlake-testdata repository if not already present locally.
    """)

    vocab_dir = ensure_omop_vocabularies(project_root=PROJECT_ROOT)
    mo.md(f"Vocabulary data ready at `{vocab_dir}`")
    return (vocab_dir,)


@app.cell
def _(PROJECT_ROOT, mo):
    import duckdb

    from pluginlake.core.config import DuckLakeSettings

    settings = DuckLakeSettings(pg_host="localhost")
    data_path = (PROJECT_ROOT / settings.data_path).resolve()
    data_path.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect()
    conn.execute("INSTALL ducklake")
    conn.execute("LOAD ducklake")
    conn.execute(
        f"ATTACH 'ducklake:postgres:{settings.pg_connection_string}' "
        f"AS ducklake (DATA_PATH '{data_path}', OVERRIDE_DATA_PATH TRUE)"
    )
    mo.md("Connected to DuckLake catalog.")
    return (conn,)


@app.cell
def _(conn, load_vocabulary_dataset, mo, vocab_dir):
    vocab_schema = "ducklake.omop_vocab"
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {vocab_schema}")

    tables = load_vocabulary_dataset(vocab_dir, validate=False)
    for table_name, df in tables.items():
        ref = f"{vocab_schema}.{table_name}"
        conn.register("_data", df.to_arrow())
        conn.execute(f"CREATE OR REPLACE TABLE {ref} AS SELECT * FROM _data")  # noqa: S608
        conn.unregister("_data")

    mo.md(f"Loaded **{len(tables)}** vocabulary tables into `{vocab_schema}`.")


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 1. Browse Vocabularies

    `get_vocabulary_info()` lists all vocabularies loaded in the catalog, or filters by a
    specific vocabulary ID. This is useful to see which coding systems are available
    (SNOMED, ICD10CM, RxNorm, etc.) and their versions.
    """)


@app.cell
def _(conn, get_vocabulary_info, mo):
    all_vocabs = get_vocabulary_info(con=conn)
    mo.md(f"**{len(all_vocabs)} vocabularies** loaded in the catalog:")
    mo.ui.table(all_vocabs)


@app.cell
def _(conn, get_vocabulary_info, mo):
    snomed_info = get_vocabulary_info("SNOMED", con=conn)
    mo.md("### SNOMED CT details")
    mo.ui.table(snomed_info)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 2. Look Up a Concept

    `get_concept()` retrieves full metadata for a single concept by its ID. Every clinical
    observation in OMOP references a `concept_id` — this function shows you what that ID means.
    """)


@app.cell
def _(conn, get_concept, mo):
    concept = get_concept(201826, con=conn)
    mo.md("### Concept 201826 — Type 2 Diabetes Mellitus")
    mo.ui.table(concept)


@app.cell
def _(conn, get_concept, mo):
    gender_male = get_concept(8507, con=conn)
    mo.md("### Concept 8507 — Male (Gender)")
    mo.ui.table(gender_male)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 3. Search Concepts

    `search_concepts()` performs a case-insensitive name search across the concept table.
    You can filter by domain (`Condition`, `Drug`, `Measurement`, etc.), vocabulary
    (`SNOMED`, `RxNorm`, etc.), and whether to include only standard concepts.
    """)


@app.cell
def _(conn, mo, search_concepts):
    diabetes_results = search_concepts("diabetes", con=conn, limit=20)
    mo.md(f"### Search: 'diabetes' (standard concepts only)\n\nFound **{len(diabetes_results)}** results:")
    mo.ui.table(diabetes_results)


@app.cell
def _(conn, mo, search_concepts):
    hypertension_conditions = search_concepts(
        "hypertension",
        domain_id="Condition",
        vocabulary_id="SNOMED",
        con=conn,
        limit=15,
    )
    mo.md(f"### Search: 'hypertension' — SNOMED Conditions only\n\nFound **{len(hypertension_conditions)}** results:")
    mo.ui.table(hypertension_conditions)


@app.cell
def _(conn, mo, search_concepts):
    metformin_results = search_concepts("metformin", domain_id="Drug", con=conn, limit=15)
    mo.md(f"### Search: 'metformin' — Drug domain\n\nFound **{len(metformin_results)}** results:")
    mo.ui.table(metformin_results)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 4. Navigate the Concept Hierarchy

    OMOP vocabularies organise concepts in a hierarchy via the `concept_ancestor` table.
    - `get_concept_descendants()` finds all children/grandchildren of a concept
    - `get_concept_ancestors()` finds all parents up to the root

    This is useful for building cohorts: instead of listing every specific diabetes code, you
    can select a parent concept and include all descendants.
    """)


@app.cell
def _(conn, get_concept_descendants, mo):
    diabetes_descendants = get_concept_descendants(201826, max_levels=2, con=conn)
    mo.md(
        f"### Descendants of 201826 (Type 2 DM), up to 2 levels\n\n"
        f"Found **{len(diabetes_descendants)}** descendant concepts:"
    )
    mo.ui.table(diabetes_descendants)


@app.cell
def _(conn, get_concept_ancestors, mo):
    diabetes_ancestors = get_concept_ancestors(201826, con=conn)
    mo.md(
        f"### Ancestors of 201826 (Type 2 DM)\n\nFound **{len(diabetes_ancestors)}** ancestor concepts (path to root):"
    )
    mo.ui.table(diabetes_ancestors)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 5. Map Source Codes

    `map_source_code()` translates local or source-system codes (e.g. ICD-10-CM) to
    standard OMOP concepts via the `source_to_concept_map` table. This is how raw clinical
    data gets mapped to the common data model.
    """)


@app.cell
def _(conn, map_source_code, mo):
    icd10_mapping = map_source_code("E11", "ICD10CM", con=conn)
    if len(icd10_mapping) > 0:
        mo.md("### ICD-10-CM E11 (Type 2 diabetes mellitus)")
        mo.ui.table(icd10_mapping)
    else:
        mo.callout(
            mo.md(
                "No mapping found for E11 / ICD10CM. "
                "The `source_to_concept_map` table may not be loaded for this vocabulary."
            ),
            kind="info",
        )


@app.cell
def _(conn, map_source_code, mo):
    hypertension_mapping = map_source_code("I10", "ICD10CM", con=conn)
    if len(hypertension_mapping) > 0:
        mo.md("### ICD-10-CM I10 (Essential hypertension)")
        mo.ui.table(hypertension_mapping)
    else:
        mo.callout(
            mo.md("No mapping found for I10 / ICD10CM."),
            kind="info",
        )


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 6. Validate Concept IDs

    `validate_concept_ids()` checks a list of concept IDs against the vocabulary and reports
    whether each is valid, standard, in the right domain, and not deprecated. This is used
    during data ingestion to catch mapping errors before they enter the warehouse.
    """)


@app.cell
def _(conn, mo, validate_concept_ids):
    test_ids = [201826, 320128, 8507, 999999, 0]
    validation = validate_concept_ids(conn, test_ids)
    mo.md(
        "### Validate a mix of concept IDs\n\n"
        "IDs: `201826` (Type 2 DM), `320128` (Hypertension), `8507` (Male), "
        "`999999` (non-existent), `0` (unmapped placeholder)"
    )
    mo.ui.table(validation)


@app.cell
def _(conn, mo, validate_concept_ids):
    condition_validation = validate_concept_ids(
        conn,
        [201826, 320128, 8507],
        domain_id="Condition",
    )
    mo.md(
        "### Validate with domain filter (Condition)\n\n`8507` is a Gender concept — it should fail the domain check."
    )
    mo.ui.table(condition_validation)


if __name__ == "__main__":
    app.run()
