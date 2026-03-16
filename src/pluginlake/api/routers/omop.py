"""OMOP ingestion endpoint — CSV upload.

- ``POST /api/v1/omop/{table_name}/csv``  — multipart CSV upload
"""

from http import HTTPStatus

from fastapi import APIRouter, HTTPException, UploadFile

from pluginlake.api.config import IngestionSettings
from pluginlake.api.routers.ingest import IngestionResponse
from pluginlake.api.services.ingestion import IngestionError
from pluginlake.api.services.omop_ingestion import OmopCsvIngestionService
from pluginlake.config import LogSettings
from pluginlake.core.dagster_client import DagsterClient
from pluginlake.omop.config import OMOPSettings
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/omop", tags=["omop"])


def _get_csv_service() -> OmopCsvIngestionService:

    ingest_settings = IngestionSettings()
    omop_settings = OMOPSettings()
    dagster_client = DagsterClient(webserver_url=ingest_settings.dagster_webserver_url)
    log_settings = LogSettings()
    return OmopCsvIngestionService(
        dagster_client=dagster_client,
        omop_settings=omop_settings,
        settings=ingest_settings,
        ingestion_log_dir=log_settings.ingestion_log_dir,
    )


@router.post(
    "/{table_name}/csv",
    status_code=HTTPStatus.CREATED,
    summary="Upload an OMOP table CSV file",
    description=(
        "Accepts a multipart CSV upload for the named OMOP table, writes it to "
        "``OMOP_RAW_DATA_DIR/{table_name}.csv``, and triggers ``omop_ingest_job`` "
        "via Dagster to materialize the asset in DuckLake.\n\n"
        "**Supported format:** .csv only"
    ),
)
async def ingest_omop_csv(table_name: str, file: UploadFile) -> IngestionResponse:
    """Ingest an OMOP table CSV file."""
    service = _get_csv_service()

    try:
        result = await service.ingest_file(file=file, dataset=table_name)
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
