"""FHIR folder ingestion sensor."""

import json
import time

from dagster import AssetKey, DefaultSensorStatus, RunRequest, SensorEvaluationContext, SensorResult, SkipReason, sensor

from pluginlake.fhir.config import get_fhir_settings
from pluginlake.fhir.translator_registry import FHIR_RESOURCE_TYPES, FHIR_TO_OMOP_TABLE


@sensor(
    job_name="fhir_ingest_job",
    minimum_interval_seconds=get_fhir_settings().folder_watch_interval,
    default_status=DefaultSensorStatus.RUNNING,
)
def fhir_folder_sensor(context: SensorEvaluationContext) -> SensorResult | SkipReason:
    """Watch FHIR_RAW_DATA_DIR for new/changed NDJSON files and trigger ingestion."""
    settings = get_fhir_settings()
    raw_dir = settings.raw_data_dir
    debounce = settings.folder_watch_debounce_seconds

    if not raw_dir.exists():
        return SkipReason(f"Directory {raw_dir} does not exist")

    previous_state: dict[str, float] = json.loads(context.cursor) if context.cursor else {}
    now = time.time()

    changed_types: list[str] = []
    new_state: dict[str, float] = {}

    for ndjson_file in raw_dir.glob("*.ndjson"):
        resource_type = ndjson_file.stem.lower()
        if resource_type not in FHIR_RESOURCE_TYPES:
            continue

        mtime = ndjson_file.stat().st_mtime

        if now - mtime < debounce:
            new_state[resource_type] = previous_state.get(resource_type, 0.0)
            continue

        new_state[resource_type] = mtime

        if resource_type not in previous_state or mtime > previous_state[resource_type]:
            changed_types.append(resource_type)

    if not changed_types:
        context.update_cursor(json.dumps(new_state))
        return SkipReason("No new or modified FHIR NDJSON files detected")

    omop_tables = {FHIR_TO_OMOP_TABLE[rt] for rt in changed_types}

    context.update_cursor(json.dumps(new_state))
    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=f"fhir-folder-{int(now)}",
                asset_selection=[AssetKey(["fhir_raw", rt]) for rt in changed_types]
                + [AssetKey(["fhir_omop_raw", t]) for t in omop_tables]
                + [AssetKey(["omop", t]) for t in omop_tables],
            )
        ]
    )
