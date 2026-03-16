"""FHIR ingestion service — NDJSON upload path."""

from pathlib import Path

from pluginlake.api.config import IngestionSettings
from pluginlake.api.services.ingestion import IngestionError, IngestionService
from pluginlake.core.dagster_client import DagsterClient, DagsterClientError
from pluginlake.fhir.config import FHIRSettings
from pluginlake.fhir.translator_registry import FHIR_TO_OMOP_TABLE
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


class FhirNdjsonIngestionService(IngestionService):
    """Ingestion service for FHIR NDJSON uploads.

    Appends the uploaded NDJSON to ``FHIR_RAW_DATA_DIR/{dataset}.ndjson`` and
    triggers ``fhir_ingest_job`` for the selected asset via Dagster.

    Args:
        dagster_client: Client for triggering Dagster jobs.
        fhir_settings: FHIR-specific configuration (provides raw_data_dir).
        settings: Ingestion-specific configuration (file size limits, etc.).
    """

    def __init__(
        self,
        dagster_client: DagsterClient,
        fhir_settings: FHIRSettings,
        settings: IngestionSettings | None = None,
        ingestion_log_dir: Path | None = None,
    ) -> None:
        """Initialise with a Dagster client, FHIR settings, and optional ingestion settings."""
        super().__init__(dagster_client=dagster_client, settings=settings, ingestion_log_dir=ingestion_log_dir)
        self._fhir_settings = fhir_settings

    def _validate_extension(self, filename: str) -> None:
        if Path(filename).suffix.lower() != ".ndjson":
            msg = "FHIR uploads must be .ndjson files."
            raise IngestionError(msg)

    def _store_file(self, content: bytes, filename: str, dataset: str, file_id: str) -> Path:  # noqa: ARG002 — signature required by IngestionService; FHIR stores by dataset name only
        dest = self._fhir_settings.raw_data_dir / f"{dataset}.ndjson"
        dest.parent.mkdir(parents=True, exist_ok=True)
        needs_separator = dest.exists() and dest.stat().st_size > 0
        with dest.open("ab") as f:
            if needs_separator:
                f.write(b"\n")
            f.write(content)
        return dest

    async def _trigger_dagster(self, file_path: Path, dataset: str, filename: str) -> str | None:  # noqa: ARG002 — signature required by IngestionService; FHIR triggers by dataset name only
        if self._dagster is None:
            msg = "_trigger_dagster requires dagster_client"
            raise TypeError(msg)
        try:
            asset_selection: list[list[str]] = [["fhir_raw", dataset]]
            omop_table = FHIR_TO_OMOP_TABLE.get(dataset)
            if omop_table:
                asset_selection.append(["fhir_omop_raw", omop_table])
                asset_selection.append(["omop", omop_table])
            result = await self._dagster.trigger_job(
                job_name="fhir_ingest_job",
                asset_selection=asset_selection,
            )
        except DagsterClientError as exc:
            logger.warning("Failed to trigger Dagster for fhir_raw/%s: %s", dataset, exc)
            return None
        else:
            return result.run_id
