"""FHIR ingestion endpoint — NDJSON upload.

- ``POST /api/v1/fhir/{resource_type}/ndjson``  — multipart NDJSON upload
"""

from http import HTTPStatus

from fastapi import APIRouter, HTTPException, UploadFile

from pluginlake.api.config import IngestionSettings
from pluginlake.api.routers.ingest import IngestionResponse
from pluginlake.api.services.fhir_ingestion import FhirNdjsonIngestionService
from pluginlake.api.services.ingestion import IngestionError
from pluginlake.config import LogSettings
from pluginlake.core.dagster_client import DagsterClient
from pluginlake.fhir.config import FHIRSettings
from pluginlake.fhir.translator_registry import FHIR_RESOURCE_TYPES
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/fhir", tags=["fhir"])


def _get_ndjson_service() -> FhirNdjsonIngestionService:
    ingest_settings = IngestionSettings()
    fhir_settings = FHIRSettings()
    dagster_client = DagsterClient(webserver_url=ingest_settings.dagster_webserver_url)
    log_settings = LogSettings()
    return FhirNdjsonIngestionService(
        dagster_client=dagster_client,
        fhir_settings=fhir_settings,
        settings=ingest_settings,
        ingestion_log_dir=log_settings.ingestion_log_dir,
    )


@router.post(
    "/{resource_type}/ndjson",
    status_code=HTTPStatus.CREATED,
    summary="Upload a FHIR resource NDJSON file",
    description=(
        "Accepts a multipart NDJSON upload for the named FHIR resource type, writes it to "
        "``FHIR_RAW_DATA_DIR/{resource_type}.ndjson``, and triggers ``fhir_ingest_job`` "
        "via Dagster to materialize the asset in DuckLake.\n\n"
        "**Supported format:** .ndjson only"
    ),
)
async def ingest_fhir_ndjson(resource_type: str, file: UploadFile) -> IngestionResponse:
    """Ingest a FHIR resource NDJSON file."""
    if resource_type not in FHIR_RESOURCE_TYPES:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=f"Unsupported FHIR resource type: {resource_type!r}. Supported: {FHIR_RESOURCE_TYPES}",
        )

    service = _get_ndjson_service()

    try:
        result = await service.ingest_file(file=file, dataset=resource_type)
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
