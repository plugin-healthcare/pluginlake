"""Tests for the data ingestion endpoint and service."""

import io
from http import HTTPStatus
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from starlette.testclient import TestClient

from pluginlake.api.app import create_app
from pluginlake.api.config import IngestionSettings
from pluginlake.api.services.ingestion import IngestionError, IngestionResult, IngestionService
from pluginlake.config import StorageLayer, StorageSettings
from pluginlake.core.dagster_client import DagsterClient, DagsterClientError, DagsterRunResult
from pluginlake.core.storage.layers import StorageLayerManager

httpx = pytest.importorskip("httpx")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_settings(tmp_path):
    return StorageSettings(base_dir=tmp_path / "data")


@pytest.fixture
def storage_manager(storage_settings):
    mgr = StorageLayerManager(settings=storage_settings)
    mgr.initialize()
    return mgr


@pytest.fixture
def dagster_client():
    return DagsterClient(webserver_url="http://localhost:3000")


@pytest.fixture
def ingest_settings():
    return IngestionSettings(max_file_size_mb=1, allowed_extensions=[".csv", ".json", ".parquet"])


@pytest.fixture
def ingestion_service(storage_manager, dagster_client, ingest_settings):
    return IngestionService(
        storage_manager=storage_manager,
        dagster_client=dagster_client,
        settings=ingest_settings,
    )


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_ingestion_settings_defaults():
    settings = IngestionSettings()
    assert settings.max_file_size_mb == 500
    assert ".csv" in settings.allowed_extensions
    assert ".parquet" in settings.allowed_extensions


def test_ingestion_settings_max_file_size_bytes():
    settings = IngestionSettings(max_file_size_mb=10)
    assert settings.max_file_size_bytes == 10 * 1024 * 1024


@pytest.mark.anyio
async def test_ingest_rejects_invalid_extension(ingestion_service):
    file = UploadFile(filename="data.txt", file=io.BytesIO(b"hello"))

    with pytest.raises(IngestionError, match="not allowed"):
        await ingestion_service.ingest_file(file=file, dataset="test")


@pytest.mark.anyio
async def test_ingest_rejects_oversized_file(ingestion_service):
    big_content = b"x" * (2 * 1024 * 1024)  # 2 MB, limit is 1 MB
    file = UploadFile(filename="big.csv", file=io.BytesIO(big_content))

    with pytest.raises(IngestionError, match="exceeds the maximum"):
        await ingestion_service.ingest_file(file=file, dataset="test")


@pytest.mark.anyio
async def test_ingest_stores_file_in_raw_layer(ingestion_service, storage_settings):
    content = b"col1,col2\na,b"
    file = UploadFile(filename="test.csv", file=io.BytesIO(content))

    with patch.object(ingestion_service._dagster, "trigger_job", new_callable=AsyncMock) as mock_trigger:
        mock_trigger.return_value = DagsterRunResult(run_id="run-123", status="STARTING")
        result = await ingestion_service.ingest_file(file=file, dataset="patients")

    assert result.status == "completed"
    assert result.dagster_run_id == "run-123"
    assert result.dataset == "patients"
    assert result.filename == "test.csv"
    assert result.size_bytes == len(content)

    stored_path = Path(result.file_path)
    assert stored_path.exists()
    assert stored_path.read_bytes() == content
    assert StorageLayer.RAW.value in str(stored_path)
    assert "patients" in str(stored_path)


@pytest.mark.anyio
async def test_ingest_succeeds_when_dagster_unavailable(ingestion_service, storage_settings):
    content = b'{"key": "value"}'
    file = UploadFile(filename="data.json", file=io.BytesIO(content))

    with patch.object(ingestion_service._dagster, "trigger_job", new_callable=AsyncMock) as mock_trigger:
        mock_trigger.side_effect = DagsterClientError("Connection refused")
        result = await ingestion_service.ingest_file(file=file, dataset="events")

    assert result.status == "stored"
    assert result.dagster_run_id is None
    assert result.dataset == "events"

    stored_path = Path(result.file_path)
    assert stored_path.exists()


@pytest.mark.anyio
async def test_dagster_client_trigger_success():
    client = DagsterClient(webserver_url="http://localhost:3000")
    mock_response = {
        "data": {
            "launchRun": {
                "__typename": "LaunchRunSuccess",
                "run": {"runId": "abc-123", "status": "STARTING"},
            },
        },
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_post.return_value = mock_resp

        result = await client.trigger_job("my_job")

    assert result.run_id == "abc-123"
    assert result.status == "STARTING"


@pytest.mark.anyio
async def test_dagster_client_trigger_python_error():
    client = DagsterClient(webserver_url="http://localhost:3000")
    mock_response = {
        "data": {
            "launchRun": {
                "__typename": "PythonError",
                "message": "Job not found",
                "stack": [],
            },
        },
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_post.return_value = mock_resp

        with pytest.raises(DagsterClientError, match="Job not found"):
            await client.trigger_job("nonexistent_job")


@pytest.mark.anyio
async def test_dagster_client_connection_error():
    client = DagsterClient(webserver_url="http://localhost:9999")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(DagsterClientError, match="Failed to connect"):
            await client.trigger_job("my_job")


def _patch_ingestion_service(result: IngestionResult | None = None, error: IngestionError | None = None):
    """Patch the ingestion service dependency in the router."""
    mock_service = AsyncMock(spec=IngestionService)
    if error:
        mock_service.ingest_file.side_effect = error
    else:
        mock_service.ingest_file.return_value = result or IngestionResult(
            file_id="abc123",
            filename="test.csv",
            dataset="patients",
            file_path="/data/raw/patients/20260226T120000_abc123_test.csv",
            size_bytes=100,
            dagster_run_id="run-456",
            status="completed",
            message="File ingested and Dagster job triggered (run_id=run-456).",
        )
    return mock_service


def test_ingest_endpoint_valid_file(client):
    mock_service = _patch_ingestion_service()

    with patch("pluginlake.api.routers.ingest._get_ingestion_service", return_value=mock_service):
        resp = client.post(
            "/api/v1/ingest",
            files={"file": ("test.csv", b"col1,col2\na,b", "text/csv")},
            data={"dataset": "patients"},
        )

    assert resp.status_code == HTTPStatus.CREATED
    body = resp.json()
    assert body["file_id"] == "abc123"
    assert body["dataset"] == "patients"
    assert body["status"] == "completed"
    assert body["dagster_run_id"] == "run-456"


def test_ingest_endpoint_invalid_extension(client):
    mock_service = _patch_ingestion_service(
        error=IngestionError("File extension '.txt' is not allowed."),
    )

    with patch("pluginlake.api.routers.ingest._get_ingestion_service", return_value=mock_service):
        resp = client.post(
            "/api/v1/ingest",
            files={"file": ("data.txt", b"hello", "text/plain")},
            data={"dataset": "test"},
        )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "not allowed" in resp.json()["detail"]


def test_ingest_endpoint_file_too_large(client):
    mock_service = _patch_ingestion_service(
        error=IngestionError("File 'big.csv' (104857600 bytes) exceeds the maximum allowed size of 1 MB."),
    )

    with patch("pluginlake.api.routers.ingest._get_ingestion_service", return_value=mock_service):
        resp = client.post(
            "/api/v1/ingest",
            files={"file": ("big.csv", b"x", "text/csv")},
            data={"dataset": "test"},
        )

    assert resp.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert "exceeds" in resp.json()["detail"].lower() or "size" in resp.json()["detail"].lower()


def test_ingest_endpoint_dagster_unavailable(client):
    mock_service = _patch_ingestion_service(
        result=IngestionResult(
            file_id="def456",
            filename="data.json",
            dataset="events",
            file_path="/data/raw/events/20260226T120000_def456_data.json",
            size_bytes=50,
            dagster_run_id=None,
            status="stored",
            message="File ingested successfully. Dagster job trigger was skipped or failed.",
        ),
    )

    with patch("pluginlake.api.routers.ingest._get_ingestion_service", return_value=mock_service):
        resp = client.post(
            "/api/v1/ingest",
            files={"file": ("data.json", b'{"key": "val"}', "application/json")},
            data={"dataset": "events"},
        )

    assert resp.status_code == HTTPStatus.CREATED
    body = resp.json()
    assert body["status"] == "stored"
    assert body["dagster_run_id"] is None


def test_ingest_endpoint_missing_dataset(client):
    resp = client.post(
        "/api/v1/ingest",
        files={"file": ("test.csv", b"data", "text/csv")},
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_ingest_endpoint_missing_file(client):
    resp = client.post(
        "/api/v1/ingest",
        data={"dataset": "test"},
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_ingest_info_endpoint(client):
    resp = client.get("/api/v1/ingest/info")
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()
    assert "max_file_size_mb" in body
    assert "allowed_extensions" in body
    assert isinstance(body["allowed_extensions"], list)
