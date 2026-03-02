"""Data ingestion endpoint for receiving files from external parties.

Provides a ``POST /api/v1/ingest`` endpoint that accepts multipart file
uploads, validates them, stores them in the raw storage layer, and triggers
a Dagster job for downstream processing.
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pluginlake.api.config import IngestionSettings
from pluginlake.api.services.ingestion import IngestionError, IngestionService
from pluginlake.config import StorageSettings
from pluginlake.core.dagster_client import DagsterClient
from pluginlake.core.storage.layers import StorageLayerManager
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


class IngestionResponse(BaseModel):
    """Response returned after a successful file ingestion.

    Attributes:
        file_id: Unique identifier assigned to the uploaded file.
        filename: Original filename.
        dataset: Target dataset name.
        file_path: Storage path where the file was written.
        size_bytes: Size of the file in bytes.
        dagster_run_id: Dagster run ID if triggered, else null.
        status: ``completed`` if Dagster was triggered, ``stored`` otherwise.
        message: Human-readable summary.
    """

    file_id: str
    filename: str
    dataset: str
    file_path: str
    size_bytes: int
    dagster_run_id: str | None
    status: str
    message: str


class ErrorResponse(BaseModel):
    """Error response body.

    Attributes:
        detail: Human-readable error description.
    """

    detail: str


class IngestionInfoResponse(BaseModel):
    """Response for the ingestion info endpoint.

    Attributes:
        max_file_size_mb: Maximum allowed file size in megabytes.
        allowed_extensions: List of allowed file extensions.
    """

    max_file_size_mb: int
    allowed_extensions: list[str]


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_ingestion_service() -> IngestionService:
    """Build the ingestion service from settings."""
    storage_settings = StorageSettings()
    ingest_settings = IngestionSettings()

    storage_manager = StorageLayerManager(settings=storage_settings)
    storage_manager.initialize()

    dagster_client = DagsterClient(webserver_url=ingest_settings.dagster_webserver_url)

    return IngestionService(
        storage_manager=storage_manager,
        dagster_client=dagster_client,
        settings=ingest_settings,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/ingest",
    status_code=HTTPStatus.CREATED,
    summary="Upload a data file for ingestion",
    description=(
        "Accepts a multipart file upload, validates file type and size, "
        "writes the file to the raw storage layer, and triggers a Dagster "
        "job for downstream processing.\n\n"
        "**Supported formats:** .csv, .json, .parquet, .ndjson, .xlsx\n\n"
        "**Max file size:** 500 MB (configurable)"
    ),
    responses={
        HTTPStatus.UNPROCESSABLE_ENTITY: {
            "model": ErrorResponse,
            "description": "Invalid file type or validation error.",
        },
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE: {
            "model": ErrorResponse,
            "description": "File exceeds the maximum allowed size.",
        },
    },
)
async def ingest_file(
    file: UploadFile,
    dataset: Annotated[str, Form(description="Target dataset name for organising the file.")],
) -> IngestionResponse:
    """Ingest an uploaded data file.

    The file is validated, stored in the raw layer under
    ``raw/{dataset}/{timestamp}_{file_id}_{filename}``, and a Dagster
    job is triggered for processing. If Dagster is unreachable, the file
    is still stored and the response indicates that processing was not
    triggered.

    Args:
        file: The uploaded file (multipart form data).
        dataset: Target dataset name (form field).

    Returns:
        IngestionResponse with file metadata and processing status.
    """
    service = _get_ingestion_service()

    try:
        result = await service.ingest_file(file=file, dataset=dataset)
    except IngestionError as exc:
        detail = str(exc)
        status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE if "size" in detail.lower() else HTTPStatus.UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status, detail=detail) from exc

    return IngestionResponse(
        file_id=result.file_id,
        filename=result.filename,
        dataset=result.dataset,
        file_path=result.file_path,
        size_bytes=result.size_bytes,
        dagster_run_id=result.dagster_run_id,
        status=result.status,
        message=result.message,
    )


@router.get(
    "/ingest/info",
    summary="Get ingestion endpoint configuration",
    description="Returns the current upload limits and allowed file types.",
)
def ingest_info() -> IngestionInfoResponse:
    """Return ingestion configuration limits."""
    settings = IngestionSettings()
    return IngestionInfoResponse(
        max_file_size_mb=settings.max_file_size_mb,
        allowed_extensions=settings.allowed_extensions,
    )
