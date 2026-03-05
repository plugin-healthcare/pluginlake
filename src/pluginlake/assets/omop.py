"""OMOP CDM Dagster assets."""

from collections.abc import Generator

from dagster import AssetExecutionContext, AssetKey, AssetOut, Output, multi_asset

from pluginlake.omop.loader import load_omop_dataset, load_vocabulary_dataset

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
    can_subset=True,
)
def omop_clinical_tables(context: AssetExecutionContext) -> Generator[Output]:
    """Load OMOP CDM clinical tables from CSV and yield each as a Dagster Output."""
    selected_tables = [key.path[-1] for key in context.selected_asset_keys]
    tables = load_omop_dataset(table_names=selected_tables)
    for key in context.selected_asset_keys:
        table_name = key.path[-1]
        if table_name in tables:
            yield Output(value=tables[table_name], output_name=table_name)


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
