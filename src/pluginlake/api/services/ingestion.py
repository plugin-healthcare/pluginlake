"""Ingestion service — validates, stores, and triggers processing of uploaded files.

Orchestrates the flow from file upload to raw storage layer and Dagster job
triggering, with proper validation and error handling.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile

from pluginlake.api.config import IngestionSettings
from pluginlake.config import StorageLayer
from pluginlake.core.dagster_client import DagsterClient, DagsterClientError
from pluginlake.core.storage.layers import StorageLayerManager
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


class IngestionError(Exception):
    """Raised when file ingestion fails due to validation or storage errors."""


@dataclass
class IngestionResult:
    """Outcome of a file ingestion operation.

    Attributes:
        file_id: Unique identifier assigned to the uploaded file.
        filename: Original filename of the upload.
        dataset: Target dataset name.
        file_path: Absolute path where the file was stored.
        size_bytes: Size of the stored file in bytes.
        dagster_run_id: Dagster run ID if a job was triggered, else None.
        status: Overall status of the ingestion.
        message: Human-readable status message.
    """

    file_id: str
    filename: str
    dataset: str
    file_path: str
    size_bytes: int
    dagster_run_id: str | None
    status: str
    message: str


class IngestionService:
    """Handles file upload validation, storage, and Dagster triggering.

    Args:
        storage_manager: Manages the medallion storage layers.
        dagster_client: Client for triggering Dagster jobs.
        settings: Ingestion-specific configuration.
    """

    def __init__(
        self,
        storage_manager: StorageLayerManager,
        dagster_client: DagsterClient,
        settings: IngestionSettings | None = None,
    ) -> None:
        """Initialise the service with storage, Dagster, and settings."""
        self._storage = storage_manager
        self._dagster = dagster_client
        self._settings = settings or IngestionSettings()

    async def ingest_file(self, file: UploadFile, dataset: str) -> IngestionResult:
        """Validate, store, and trigger processing for an uploaded file.

        Args:
            file: The uploaded file from the HTTP request.
            dataset: Target dataset name for organising the file.

        Returns:
            An IngestionResult describing the outcome.

        Raises:
            IngestionError: If validation fails (extension, size).
        """
        filename = file.filename or "unnamed"
        file_id = uuid.uuid4().hex[:12]

        logger.info("Ingesting file %r for dataset %r (file_id=%s)", filename, dataset, file_id)

        self._validate_extension(filename)
        content = await self._read_and_validate_size(file, filename)
        file_path = self._store_file(content, filename, dataset, file_id)
        dagster_run_id = await self._trigger_dagster(file_path, dataset, filename)

        status = "completed" if dagster_run_id else "stored"
        message = (
            f"File ingested and Dagster job triggered (run_id={dagster_run_id})."
            if dagster_run_id
            else "File ingested successfully. Dagster job trigger was skipped or failed."
        )

        logger.info(
            "Ingestion %s: file_id=%s, dataset=%s, path=%s, dagster_run=%s",
            status,
            file_id,
            dataset,
            file_path,
            dagster_run_id,
        )

        return IngestionResult(
            file_id=file_id,
            filename=filename,
            dataset=dataset,
            file_path=str(file_path),
            size_bytes=len(content),
            dagster_run_id=dagster_run_id,
            status=status,
            message=message,
        )

    def _validate_extension(self, filename: str) -> None:
        """Check that the file extension is in the allowed list."""
        suffix = Path(filename).suffix.lower()
        if suffix not in self._settings.allowed_extensions:
            msg = f"File extension {suffix!r} is not allowed. Allowed: {', '.join(self._settings.allowed_extensions)}"
            raise IngestionError(msg)

    async def _read_and_validate_size(self, file: UploadFile, filename: str) -> bytes:
        """Read the full file content and validate against the size limit."""
        content = await file.read()
        if len(content) > self._settings.max_file_size_bytes:
            msg = (
                f"File {filename!r} ({len(content)} bytes) exceeds the maximum "
                f"allowed size of {self._settings.max_file_size_mb} MB."
            )
            raise IngestionError(msg)
        return content

    def _store_file(
        self,
        content: bytes,
        filename: str,
        dataset: str,
        file_id: str,
    ) -> Path:
        """Write the file content to the raw storage layer.

        Files are stored as: ``raw/{dataset}/{timestamp}_{file_id}_{filename}``
        """
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S")
        stored_name = f"{timestamp}_{file_id}_{filename}"
        dest = self._storage.get_path(StorageLayer.RAW, dataset, stored_name)

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

        logger.info("Stored file at %s (%d bytes)", dest, len(content))
        return dest

    async def _trigger_dagster(
        self,
        file_path: Path,
        dataset: str,
        filename: str,
    ) -> str | None:
        """Attempt to trigger a Dagster job for the ingested file.

        Returns the run ID on success, or None if triggering fails.
        Failures are logged but do not raise — the file is already stored.
        """
        try:
            result = await self._dagster.trigger_job(
                job_name=self._settings.dagster_job_name,
                run_config={
                    "ops": {
                        "process_raw_file": {
                            "config": {
                                "file_path": str(file_path),
                                "dataset": dataset,
                                "filename": filename,
                            },
                        },
                    },
                },
            )
        except DagsterClientError:
            logger.warning(
                "Failed to trigger Dagster job for %r (dataset=%r). "
                "File was stored successfully — processing can be triggered manually.",
                filename,
                dataset,
                exc_info=True,
            )
            return None
        else:
            return result.run_id
