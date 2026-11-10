"""Tests for the Dagster to OpenLineage bridge."""

import logging
from unittest.mock import MagicMock

import pytest
import requests
from dagster import (
    AssetKey,
    DagsterInstance,
    Definitions,
    MaterializeResult,
    MetadataValue,
    TableColumn,
    TableColumnDep,
    TableColumnLineage,
    TableSchema,
    asset,
    materialize,
)
from openlineage.client.event_v2 import RunState
from openlineage.client.serde import Serde
from openlineage.client.transport.http import HttpTransport

from pluginlake.core.lineage.config import LineageSettings
from pluginlake.core.lineage.openlineage_bridge import (
    build_dataset_facets,
    build_job_facets,
    build_output_facets,
    build_run_events,
    create_client,
    dataset_name,
    emit_run_events,
)

_RAW_KEY = AssetKey(["omop_raw", "person"])
_PERSON_KEY = AssetKey(["omop", "person"])
_PATIENT_NAME = "Jan Jansen"


@asset(key=_RAW_KEY, kinds={"polars"})
def raw_person() -> MaterializeResult:
    return MaterializeResult(
        metadata={
            "dagster/row_count": 3,
            "dagster/column_schema": TableSchema(columns=[TableColumn(name="person_id", type="BIGINT")]),
            "preview": MetadataValue.md(f"| person_id | name |\n|---|---|\n| 1 | {_PATIENT_NAME} |"),
        },
    )


@asset(key=_PERSON_KEY, deps=[raw_person])
def person() -> MaterializeResult:
    return MaterializeResult(
        metadata={
            "dagster/column_lineage": TableColumnLineage(
                deps_by_column={"person_id": [TableColumnDep(asset_key=_RAW_KEY, column_name="person_id")]},
            ),
        },
    )


@pytest.fixture
def settings() -> LineageSettings:
    return LineageSettings(url="http://marquez:5000")


@pytest.fixture(scope="module")
def run_events():
    instance = DagsterInstance.ephemeral()
    result = materialize([raw_person, person], instance=instance)
    dagster_run = instance.get_run_by_id(result.run_id)
    assert dagster_run is not None
    repository_def = Definitions(assets=[raw_person, person]).get_repository_def()
    return build_run_events(
        dagster_run,
        instance,
        repository_def,
        LineageSettings(url="http://marquez:5000", job_namespace="ds-test-001"),
    )


def test_dataset_name_is_ducklake_table_ref():
    assert dataset_name(_PERSON_KEY) == "ducklake.omop.person"
    assert dataset_name(AssetKey(["titanic"])) == "ducklake.main.titanic"


@pytest.mark.parametrize(
    ("kinds", "integration", "job_type"),
    [({"dbt", "duckdb"}, "DBT", "MODEL"), ({"polars"}, "DAGSTER", "POLARS"), (set(), "DAGSTER", "ASSET")],
)
def test_build_job_facets_maps_kinds(kinds: set[str], integration: str, job_type: str):
    facet = build_job_facets(kinds)["jobType"]
    assert (facet.integration, facet.jobType, facet.processingType) == (integration, job_type, "BATCH")


def test_build_dataset_facets_without_metadata_is_empty():
    assert build_dataset_facets({}, "ducklake") == {}


def test_build_dataset_facets_translates_schema_and_column_lineage():
    metadata = {
        "dagster/column_schema": MetadataValue.table_schema(TableSchema(columns=[TableColumn(name="id", type="INT")])),
        "dagster/column_lineage": MetadataValue.column_lineage(
            TableColumnLineage(deps_by_column={"id": [TableColumnDep(asset_key=_RAW_KEY, column_name="src_id")]}),
        ),
    }
    facets = build_dataset_facets(metadata, "ducklake")
    assert [(f.name, f.type) for f in facets["schema"].fields] == [("id", "INT")]
    input_field = facets["columnLineage"].fields["id"].inputFields[0]
    assert (input_field.namespace, input_field.name, input_field.field) == (
        "ducklake",
        "ducklake.omop_raw.person",
        "src_id",
    )


def test_build_output_facets_uses_row_count():
    assert build_output_facets({"dagster/row_count": MetadataValue.int(7)})["outputStatistics"].rowCount == 7
    assert build_output_facets({}) == {}


def test_build_run_events_one_complete_event_per_asset(run_events):
    assert [event.job.name for event in run_events] == ["omop_raw/person", "omop/person"]
    assert all(event.eventType == RunState.COMPLETE for event in run_events)


def test_build_run_events_links_upstream_inputs(run_events):
    raw_event, person_event = run_events
    assert raw_event.inputs == []
    assert [d.name for d in person_event.inputs] == ["ducklake.omop_raw.person"]
    assert [d.name for d in person_event.outputs] == ["ducklake.omop.person"]


def test_build_run_events_carries_metadata_facets(run_events):
    raw_event, person_event = run_events
    raw_output = raw_event.outputs[0]
    assert raw_output.outputFacets["outputStatistics"].rowCount == 3
    assert [f.name for f in raw_output.facets["schema"].fields] == ["person_id"]
    assert raw_event.job.facets["jobType"].jobType == "POLARS"
    assert "person_id" in person_event.outputs[0].facets["columnLineage"].fields


def test_build_run_events_run_ids_are_unique_per_asset(run_events):
    assert len({event.run.runId for event in run_events}) == len(run_events)


def test_create_client_uses_http_transport(settings: LineageSettings):
    assert isinstance(create_client(settings).transport, HttpTransport)


def test_create_client_requires_url():
    with pytest.raises(ValueError, match="OPENLINEAGE_URL"):
        create_client(LineageSettings(url=None))


def test_settings_read_standard_openlineage_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENLINEAGE_URL", "http://marquez:5000")
    monkeypatch.setenv("OPENLINEAGE_NAMESPACE", "ds-test-001")
    settings = LineageSettings()
    assert settings.enabled
    assert (settings.url, settings.job_namespace) == ("http://marquez:5000", "ds-test-001")


def test_build_run_events_uses_node_namespace(run_events):
    assert {event.job.namespace for event in run_events} == {"ds-test-001"}


def test_events_contain_no_data_values(run_events):
    payload = "".join(Serde.to_json(event) for event in run_events)
    assert _PATIENT_NAME not in payload


def test_emit_run_events_skips_rejected_event_and_continues(run_events, caplog: pytest.LogCaptureFixture):
    client = MagicMock()
    client.emit.side_effect = [requests.HTTPError("400 Bad Request"), None]
    assert emit_run_events(client, run_events) == 1
    assert client.emit.call_count == 2
    assert "Failed to emit OpenLineage event" in caplog.text


def test_emit_run_events_stops_with_warning_when_backend_unreachable(run_events, caplog: pytest.LogCaptureFixture):
    client = MagicMock()
    client.emit.side_effect = requests.ConnectionError("Name or service not known")
    with caplog.at_level(logging.WARNING):
        assert emit_run_events(client, run_events) == 0
    assert client.emit.call_count == 1
    assert [r.levelno for r in caplog.records if "unreachable" in r.getMessage()] == [logging.WARNING]


def test_emit_run_events_unreachable_backend_does_not_raise(run_events, caplog: pytest.LogCaptureFixture):
    client = create_client(LineageSettings(url="http://127.0.0.1:9", timeout=0.5, retries=0))
    assert emit_run_events(client, run_events) == 0
    assert "OpenLineage backend unreachable" in caplog.text
