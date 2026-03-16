"""OMOP ingestion service — CSV upload path."""

from pathlib import Path

from pluginlake.api.config import IngestionSettings
from pluginlake.api.services.ingestion import IngestionError, IngestionService
from pluginlake.core.dagster_client import DagsterClient, DagsterClientError
from pluginlake.omop.config import OMOPSettings
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


class OmopCsvIngestionService(IngestionService):
    """Ingestion service for OMOP CSV uploads.

    Stores the uploaded CSV to ``OMOP_RAW_DATA_DIR/{dataset}.csv`` and
    triggers ``omop_ingest_job`` for the selected asset via Dagster.

    Args:
        dagster_client: Client for triggering Dagster jobs.
        omop_settings: OMOP-specific configuration (provides raw_data_dir).
        settings: Ingestion-specific configuration (file size limits, etc.).
    """

    def __init__(
        self,
        dagster_client: DagsterClient,
        omop_settings: OMOPSettings,
        settings: IngestionSettings | None = None,
        ingestion_log_dir: Path | None = None,
    ) -> None:
        """Initialise with a Dagster client, OMOP settings, and optional ingestion settings."""
        super().__init__(dagster_client=dagster_client, settings=settings, ingestion_log_dir=ingestion_log_dir)
        self._omop_settings = omop_settings

    def _validate_extension(self, filename: str) -> None:
        if Path(filename).suffix.lower() != ".csv":
            msg = "OMOP table uploads must be .csv files."
            raise IngestionError(msg)

    def _store_file(self, content: bytes, filename: str, dataset: str, file_id: str) -> Path:  # noqa: ARG002 — signature required by IngestionService; OMOP stores by dataset name only
        dest = self._omop_settings.raw_data_dir / f"{dataset}.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return dest

    async def _trigger_dagster(self, file_path: Path, dataset: str, filename: str) -> str | None:  # noqa: ARG002 — signature required by IngestionService; OMOP triggers by dataset name only
        if self._dagster is None:
            msg = "_trigger_dagster requires dagster_client"
            raise TypeError(msg)
        try:
            result = await self._dagster.trigger_job(
                job_name="omop_ingest_job",
                asset_selection=[["omop", dataset]],
            )
        except DagsterClientError as exc:
            logger.warning("Failed to trigger Dagster for omop/%s: %s", dataset, exc)
            return None
        else:
            return result.run_id
