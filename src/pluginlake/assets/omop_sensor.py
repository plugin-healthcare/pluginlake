"""OMOP folder ingestion sensor."""

import json
import time

from dagster import AssetKey, DefaultSensorStatus, RunRequest, SensorEvaluationContext, SensorResult, SkipReason, sensor

from pluginlake.assets.omop import CLINICAL_TABLES
from pluginlake.omop.config import get_omop_settings


@sensor(
    job_name="omop_ingest_job",
    minimum_interval_seconds=get_omop_settings().folder_watch_interval,
    default_status=DefaultSensorStatus.RUNNING,
)
def omop_folder_sensor(context: SensorEvaluationContext) -> SensorResult | SkipReason:
    """Watch OMOP_RAW_DATA_DIR for new/changed CSVs and trigger ingestion."""
    settings = get_omop_settings()
    raw_dir = settings.raw_data_dir
    debounce = settings.folder_watch_debounce_seconds

    if not raw_dir.exists():
        return SkipReason(f"Directory {raw_dir} does not exist")

    if settings.validate_concepts:
        concept_key = AssetKey(["omop_vocab", "concept"])
        event = context.instance.get_latest_materialization_event(concept_key)
        if event is None:
            return SkipReason("Waiting for vocabulary tables to be materialized first")

    previous_state: dict[str, float] = json.loads(context.cursor) if context.cursor else {}
    now = time.time()

    changed_tables: list[str] = []
    new_state: dict[str, float] = {}

    for csv_file in raw_dir.glob("*.csv"):
        table_name = csv_file.stem
        if table_name not in CLINICAL_TABLES:
            continue

        mtime = csv_file.stat().st_mtime

        if now - mtime < debounce:
            new_state[table_name] = previous_state.get(table_name, 0.0)
            continue

        new_state[table_name] = mtime

        if table_name not in previous_state or mtime > previous_state[table_name]:
            changed_tables.append(table_name)

    if not changed_tables:
        context.update_cursor(json.dumps(new_state))
        return SkipReason("No new or modified OMOP CSV files detected")

    context.update_cursor(json.dumps(new_state))
    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=f"omop-folder-{int(now)}",
                asset_selection=[AssetKey(["omop_raw", t]) for t in changed_tables]
                + [AssetKey(["omop", t]) for t in changed_tables],
            )
        ]
    )
