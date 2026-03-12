"""Tests for pluginlake.api.services.fhir_ingestion."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pluginlake.api.services.fhir_ingestion import FhirNdjsonIngestionService
from pluginlake.api.services.ingestion import IngestionError
from pluginlake.fhir.config import FHIRSettings


@pytest.fixture
def fhir_settings(tmp_path):
    return FHIRSettings(raw_data_dir=tmp_path / "fhir_raw")


@pytest.fixture
def dagster_client():
    client = MagicMock()
    client.trigger_job = AsyncMock(return_value=MagicMock(run_id="run-123"))
    return client


@pytest.fixture
def service(dagster_client, fhir_settings):
    return FhirNdjsonIngestionService(
        dagster_client=dagster_client,
        fhir_settings=fhir_settings,
    )


def test_validate_extension_accepts_ndjson(service):
    service._validate_extension("data.ndjson")


def test_validate_extension_rejects_csv(service):
    with pytest.raises(IngestionError, match="ndjson"):
        service._validate_extension("data.csv")


def test_store_file_creates_ndjson(service, fhir_settings):
    content = b'{"id": "1"}\n'
    path = service._store_file(content, "data.ndjson", "patient", "abc123")
    assert path == fhir_settings.raw_data_dir / "patient.ndjson"
    assert path.read_bytes() == content


@pytest.mark.anyio
async def test_trigger_dagster(service, dagster_client, tmp_path):
    run_id = await service._trigger_dagster(tmp_path / "test.ndjson", "patient", "patient.ndjson")
    assert run_id == "run-123"
    dagster_client.trigger_job.assert_called_once_with(
        job_name="fhir_ingest_job",
        asset_selection=[["fhir_raw", "patient"]],
    )
