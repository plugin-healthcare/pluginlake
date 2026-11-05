"""Ingestion service — validates, stores, and triggers processing of uploaded files.

Orchestrates the flow from file upload to raw storage layer and Dagster job
triggering, with proper validation and error handling.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from pluginlake.api.config import IngestionSettings
from pluginlake.config import StorageLayer
from pluginlake.core.dagster_client import DagsterClient, DagsterClientError
from pluginlake.core.storage.layers import StorageLayerManager
from pluginlake.utils.jsonl_writer import write_ingestion_log
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

# One path segment: no separators, and cannot be "." or "..".
_DATASET_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_COPY_CHUNK_BYTES = 1024 * 1024


class IngestionError(Exception):
    """Raised when an uploaded file is rejected.

    Attributes:
        status_code: HTTP status the API returns for this error.
    """

    status_code: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY


class FileTooLargeError(IngestionError):
    """Raised when an uploaded file exceeds the configured size limit."""

    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def safe_filename(filename: str | None) -> str:
    """Return the base name of a client-supplied filename.

    Directory parts (with either path separator) are dropped so the name can
    never point outside the target directory.
    """
    name = PureWindowsPath(filename or "").name
    return name if name not in {"", ".", ".."} else "unnamed"


def validate_dataset(dataset: str) -> None:
    """Check that a dataset name is a single safe path segment.

    Raises:
        IngestionError: If the name contains separators or other unsafe characters.
    """
    if not _DATASET_PATTERN.match(dataset):
        msg = (
            f"Invalid dataset name {dataset!r}. Use letters, digits, '.', '_' or '-', "
            "starting with a letter or digit (max 128 characters)."
        )
        raise IngestionError(msg)


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
        ingestion_log_dir: Directory for the JSONL ingestion log; ``None`` disables it.
    """

    def __init__(
        self,
        storage_manager: StorageLayerManager,
        dagster_client: DagsterClient,
        settings: IngestionSettings | None = None,
        ingestion_log_dir: Path | None = None,
    ) -> None:
        """Initialise the service with storage, Dagster, and settings."""
        self._storage = storage_manager
        self._dagster = dagster_client
        self._settings = settings or IngestionSettings()
        self._ingestion_log_dir = ingestion_log_dir

    async def ingest_file(self, file: UploadFile, dataset: str) -> IngestionResult:
        """Validate, store, and trigger processing for an uploaded file.

        Args:
            file: The uploaded file from the HTTP request.
            dataset: Target dataset name for organising the file.

        Returns:
            An IngestionResult describing the outcome.

        Raises:
            IngestionError: If validation fails (extension, dataset name, size).
        """
        filename = safe_filename(file.filename)
        file_id = uuid.uuid4().hex[:12]

        logger.info("Ingesting file %r for dataset %r (file_id=%s)", filename, dataset, file_id)

        self._validate_extension(filename)
        validate_dataset(dataset)
        if file.size is not None and file.size > self._settings.max_file_size_bytes:
            raise FileTooLargeError(self._too_large_message(filename))
        file_path, size_bytes = await self._store_file(file, filename, dataset, file_id)
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

        result = IngestionResult(
            file_id=file_id,
            filename=filename,
            dataset=dataset,
            file_path=str(file_path),
            size_bytes=size_bytes,
            dagster_run_id=dagster_run_id,
            status=status,
            message=message,
        )

        if self._ingestion_log_dir is not None:
            write_ingestion_log(
                self._ingestion_log_dir,
                file_id=result.file_id,
                filename=result.filename,
                dataset=result.dataset,
                size_bytes=result.size_bytes,
                status=result.status,
                dagster_run_id=result.dagster_run_id,
            )

        return result

    def _validate_extension(self, filename: str) -> None:
        """Check that the file extension is in the allowed list."""
        suffix = Path(filename).suffix.lower()
        if suffix not in self._settings.allowed_extensions:
            msg = f"File extension {suffix!r} is not allowed. Allowed: {', '.join(self._settings.allowed_extensions)}"
            raise IngestionError(msg)

    def _too_large_message(self, filename: str) -> str:
        return f"File {filename!r} exceeds the maximum allowed size of {self._settings.max_file_size_mb} MB."

    async def _store_file(
        self,
        file: UploadFile,
        filename: str,
        dataset: str,
        file_id: str,
    ) -> tuple[Path, int]:
        """Stream the upload to the raw storage layer.

        Files are stored as ``raw/{dataset}/{timestamp}_{file_id}_{filename}``.
        The upload is copied in chunks, so it is never held in memory as a whole;
        a partially written file is removed if the copy fails.

        Returns:
            The stored path and its size in bytes.
        """
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S")
        dest = self._storage.get_path(StorageLayer.RAW, dataset, f"{timestamp}_{file_id}_{filename}")
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            size = await run_in_threadpool(self._copy_with_limit, file.file, dest, filename)
        except BaseException:
            dest.unlink(missing_ok=True)
            raise

        logger.info("Stored file at %s (%d bytes)", dest, size)
        return dest, size

    def _copy_with_limit(self, source: BinaryIO, dest: Path, filename: str) -> int:
        """Copy ``source`` to ``dest`` and stop as soon as the size limit is exceeded."""
        limit = self._settings.max_file_size_bytes
        size = 0
        with dest.open("wb") as out:
            while chunk := source.read(_COPY_CHUNK_BYTES):
                size += len(chunk)
                if size > limit:
                    raise FileTooLargeError(self._too_large_message(filename))
                out.write(chunk)
        return size

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
