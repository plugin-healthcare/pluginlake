"""OMOP CDM Dagster assets."""

from collections.abc import Generator

import polars as pl
from dagster import AssetExecutionContext, AssetKey, AssetOut, Output, multi_asset

from pluginlake.core.ducklake.setup import setup_ducklake
from pluginlake.omop.config import get_omop_settings
from pluginlake.omop.loader import load_omop_dataset, load_vocabulary_dataset
from pluginlake.omop.vocabulary_validation import validate_table_concepts

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
    outs={t: AssetOut(key=AssetKey(["omop", t]), is_required=False) for t in CLINICAL_TABLES},
    deps=[AssetKey(["omop_vocab", "concept"])],
    can_subset=True,
)
def omop_clinical_tables(context: AssetExecutionContext) -> Generator[Output]:
    """Load OMOP CDM clinical tables from CSV and yield each as a Dagster Output."""
    settings = get_omop_settings()
    selected_tables = [key.path[-1] for key in context.selected_asset_keys]
    tables = load_omop_dataset(table_names=selected_tables)

    conn = None
    try:
        if settings.validate_concepts:
            conn = setup_ducklake()

        for key in context.selected_asset_keys:
            table_name = key.path[-1]
            if table_name not in tables:
                continue

            df = tables[table_name]
            metadata: dict[str, int | list[dict[str, object]]] = {"row_count": len(df)}

            if conn is not None:
                result = validate_table_concepts(
                    conn,
                    df,
                    table_name,
                    schema=f"ducklake.{settings.vocabulary_schema}",
                )
                invalid = result.filter(~pl.col("is_valid"))
                metadata["invalid_concept_count"] = invalid.height
                if invalid.height > 0:
                    summary = invalid.group_by("column_name").agg(
                        pl.col("concept_id").head(5).alias("sample_ids"),
                        pl.len().alias("count"),
                    )
                    metadata["invalid_concepts"] = summary.to_dicts()

            yield Output(value=df, output_name=table_name, metadata=metadata)
    finally:
        if conn is not None:
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
