"""OMOP CDM Dagster assets."""

from collections.abc import Generator

import duckdb
import polars as pl
from dagster import AssetExecutionContext, AssetKey, AssetOut, Output, multi_asset

from pluginlake.core.ducklake.setup import setup_ducklake
from pluginlake.omop.config import get_omop_settings
from pluginlake.omop.loader import load_omop_dataset, load_vocabulary_dataset
from pluginlake.omop.vocabulary_validation import (
    filter_invalid_rows,
    validate_table_concepts,
    write_audit_table,
)

CLINICAL_TABLES = [
    "person",
    "observation_period",
    "visit_occurrence",
    "visit_detail",
    "condition_occurrence",
    "drug_exposure",
    "procedure_occurrence",
    "device_exposure",
    "measurement",
    "observation",
    "death",
    "note",
    "note_nlp",
    "specimen",
    "condition_era",
    "drug_era",
    "fact_relationship",
]

VOCABULARY_TABLES = [
    "concept",
    "vocabulary",
    "domain",
    "concept_class",
    "concept_relationship",
    "relationship",
    "concept_synonym",
    "concept_ancestor",
    "source_to_concept_map",
    "drug_strength",
]


@multi_asset(
    outs={t: AssetOut(key=AssetKey(["omop_raw", t]), is_required=False) for t in CLINICAL_TABLES},
    can_subset=True,
)
def omop_raw_clinical_tables(context: AssetExecutionContext) -> Generator[Output]:
    """Load OMOP CDM clinical tables from CSV into the raw layer."""
    selected_tables = [key.path[-1] for key in context.selected_asset_keys]
    tables = load_omop_dataset(table_names=selected_tables)
    for key in context.selected_asset_keys:
        table_name = key.path[-1]
        if table_name not in tables:
            continue
        df = tables[table_name]
        yield Output(value=df, output_name=table_name, metadata={"row_count": len(df)})


@multi_asset(
    outs={t: AssetOut(key=AssetKey(["omop", t]), is_required=False) for t in CLINICAL_TABLES},
    deps=[AssetKey(["omop_vocab", "concept"])] + [AssetKey(["omop_raw", t]) for t in CLINICAL_TABLES],
    can_subset=True,
)
def omop_clinical_tables(context: AssetExecutionContext) -> Generator[Output]:
    """Validate raw OMOP data against vocabularies and yield clean rows.

    Reads from the raw layer, validates concept IDs, filters out invalid
    rows, and writes audit results to ``ducklake.omop_audit``.
    """
    settings = get_omop_settings()
    conn = setup_ducklake()
    try:
        for key in context.selected_asset_keys:
            table_name = key.path[-1]
            raw_ref = f"ducklake.omop_raw.{table_name}"

            try:
                df = conn.sql(f"SELECT * FROM {raw_ref}").pl()  # noqa: S608 — table ref from trusted asset key
            except duckdb.CatalogException:
                context.log.warning("Raw table %s not found, skipping", raw_ref)
                continue

            metadata: dict[str, int | list[dict[str, object]]] = {
                "raw_row_count": len(df),
            }

            if settings.validate_concepts:
                result = validate_table_concepts(
                    conn,
                    df,
                    table_name,
                    schema=f"ducklake.{settings.vocabulary_schema}",
                )
                valid_df, _invalid_df = filter_invalid_rows(df, result, table_name)

                write_audit_table(
                    conn,
                    result,
                    table_name,
                    schema=f"ducklake.{settings.audit_schema}",
                )

                invalid = result.filter(~pl.col("is_valid"))
                metadata["row_count"] = valid_df.height
                metadata["filtered_row_count"] = df.height - valid_df.height
                metadata["invalid_concept_count"] = invalid.height
                if invalid.height > 0:
                    summary = invalid.group_by("column_name").agg(
                        pl.col("concept_id").head(5).alias("sample_ids"),
                        pl.len().alias("count"),
                    )
                    metadata["invalid_concepts"] = summary.to_dicts()

                yield Output(value=valid_df, output_name=table_name, metadata=metadata)
            else:
                metadata["row_count"] = len(df)
                yield Output(value=df, output_name=table_name, metadata=metadata)
    finally:
        conn.close()


@multi_asset(
    outs={t: AssetOut(key=AssetKey(["omop_vocab", t]), is_required=False) for t in VOCABULARY_TABLES},
    can_subset=True,
)
def omop_vocabulary_tables(context: AssetExecutionContext) -> Generator[Output]:
    """Load OMOP vocabulary tables from CSV and yield each as a Dagster Output."""
    selected_tables = [key.path[-1] for key in context.selected_asset_keys]
    tables = load_vocabulary_dataset(table_names=selected_tables)
    for key in context.selected_asset_keys:
        table_name = key.path[-1]
        if table_name in tables:
            yield Output(value=tables[table_name], output_name=table_name)
