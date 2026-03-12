"""OMOP vocabulary auto-download and ingestion sensor."""

import json
import time

from dagster import AssetKey, DefaultSensorStatus, RunRequest, SensorEvaluationContext, SensorResult, SkipReason, sensor

from pluginlake.assets.omop import VOCABULARY_TABLES
from pluginlake.omop.config import get_omop_settings
from pluginlake.omop.loader import VOCABULARY_FILE_MAPPING, _find_vocabulary_file
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


@sensor(
    job_name="omop_vocab_ingest_job",
    minimum_interval_seconds=get_omop_settings().folder_watch_interval,
    default_status=DefaultSensorStatus.RUNNING,
)
def omop_vocab_sensor(context: SensorEvaluationContext) -> SensorResult | SkipReason:
    """Auto-download OMOP vocabularies if missing, then trigger ingestion for new/changed files."""
    settings = get_omop_settings()

    if not settings.vocabulary_auto_load:
        return SkipReason("vocabulary_auto_load is disabled")

    vocab_dir = settings.vocabulary_dir

    if not vocab_dir.exists() or not any(vocab_dir.iterdir()):
        try:
            from pluginlake.utils.testdata import ensure_omop_vocabularies  # noqa: PLC0415

            ensure_omop_vocabularies()
            logger.info("Downloaded OMOP vocabularies to %s", vocab_dir)
        except Exception:
            logger.exception("Failed to download OMOP vocabularies")
            return SkipReason("Vocabulary download failed, will retry next tick")

    previous_state: dict[str, float] = json.loads(context.cursor) if context.cursor else {}
    now = time.time()
    debounce = settings.folder_watch_debounce_seconds

    changed_tables: list[str] = []
    new_state: dict[str, float] = {}

    for table_name in VOCABULARY_TABLES:
        file_variants = VOCABULARY_FILE_MAPPING.get(table_name)
        if not file_variants:
            continue

        file_path = _find_vocabulary_file(vocab_dir, table_name, file_variants)
        if not file_path:
            continue

        mtime = file_path.stat().st_mtime

        if now - mtime < debounce:
            new_state[table_name] = previous_state.get(table_name, 0.0)
            continue

        new_state[table_name] = mtime

        if table_name not in previous_state or mtime > previous_state[table_name]:
            changed_tables.append(table_name)

    if not changed_tables:
        context.update_cursor(json.dumps(new_state))
        return SkipReason("No new or modified OMOP vocabulary files detected")

    context.update_cursor(json.dumps(new_state))
    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=f"omop-vocab-{int(now)}",
                asset_selection=[AssetKey(["omop_vocab", t]) for t in changed_tables],
            )
        ]
    )
