"""FHIR Dagster assets — raw NDJSON loading and FHIR-to-OMOP translation."""

from collections.abc import Generator

import duckdb
import orjson
import polars as pl
from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetOut,
    AutomationCondition,
    Output,
    multi_asset,
)

from pluginlake.core.ducklake.setup import setup_ducklake
from pluginlake.fhir.loader import load_fhir_dataset
from pluginlake.fhir.translator_registry import (
    FHIR_RESOURCE_TYPES,
    OMOP_TABLE_TO_FHIR,
    OMOP_TARGET_TABLES,
    get_translator,
)


@multi_asset(
    outs={rt: AssetOut(key=AssetKey(["fhir_raw", rt]), is_required=False) for rt in FHIR_RESOURCE_TYPES},
    can_subset=True,
)
def fhir_raw_tables(context: AssetExecutionContext) -> Generator[Output]:
    """Load FHIR NDJSON files into the raw layer as single-column json_data DataFrames."""
    selected = [key.path[-1] for key in context.selected_asset_keys]
    tables = load_fhir_dataset(resource_types=selected)
    for key in context.selected_asset_keys:
        resource_type = key.path[-1]
        if resource_type not in tables:
            continue
        df = tables[resource_type]
        yield Output(value=df, output_name=resource_type, metadata={"row_count": len(df)})


@multi_asset(
    outs={
        t: AssetOut(
            key=AssetKey(["fhir_omop_raw", t]),
            is_required=False,
            automation_condition=AutomationCondition.eager(),
        )
        for t in OMOP_TARGET_TABLES
    },
    deps=[AssetKey(["fhir_raw", rt]) for rt in FHIR_RESOURCE_TYPES],
    internal_asset_deps={
        omop_table: {AssetKey(["fhir_raw", ft]) for ft in fhir_types}
        for omop_table, fhir_types in OMOP_TABLE_TO_FHIR.items()
    },
    can_subset=True,
)
def fhir_to_omop_tables(context: AssetExecutionContext) -> Generator[Output]:
    """Translate raw FHIR data to OMOP CDM format using plugin-rosetta."""
    conn = setup_ducklake()
    try:
        for key in context.selected_asset_keys:
            omop_table = key.path[-1]
            fhir_types = OMOP_TABLE_TO_FHIR.get(omop_table, [])

            all_rows: list[dict] = []
            for fhir_type in fhir_types:
                raw_ref = f"ducklake.fhir_raw.{fhir_type}"
                try:
                    raw_df = conn.sql(f"SELECT json_data FROM {raw_ref}").pl()  # noqa: S608 — table ref from trusted asset key
                except duckdb.CatalogException:
                    context.log.warning("Raw table %s not found, skipping", raw_ref)
                    continue

                translator = get_translator(fhir_type)
                for row in raw_df.get_column("json_data").to_list():
                    record = orjson.loads(row)
                    translated = translator.translate_record(record)
                    if translated:
                        all_rows.append(translated)

            if not all_rows:
                context.log.info("No rows translated for %s", omop_table)
                continue

            df = pl.DataFrame(all_rows, infer_schema_length=None)
            yield Output(
                value=df,
                output_name=omop_table,
                metadata={"row_count": len(df), "source_fhir_types": fhir_types},
            )
    finally:
        conn.close()
