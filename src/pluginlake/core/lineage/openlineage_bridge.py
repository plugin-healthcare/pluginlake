"""Dagster to OpenLineage bridge (ADR-007).

Translates the asset materializations of a successful Dagster run into OpenLineage
``RunEvent``s and sends them to an OpenLineage HTTP backend such as Marquez. Lineage
is captured at the Dagster asset boundary: the bridge only reads what a
materialization already carries (upstream assets from the asset graph, plus the
``dagster/column_schema``, ``dagster/row_count`` and ``dagster/column_lineage``
metadata). Other metadata is never copied, so events describe jobs and datasets
but carry no data values (no patient data). ``openlineage-dagster`` is unmaintained
and pins ``dagster<=1.6.9``, so this follows the bridge pattern of srdp
(https://github.com/srdp-hub/srdp).
"""

import uuid
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from datetime import UTC, datetime

import requests
from dagster import (
    AssetKey,
    DagsterInstance,
    DagsterRun,
    IntMetadataValue,
    MetadataValue,
    RepositoryDefinition,
    TableColumnLineageMetadataValue,
    TableSchemaMetadataValue,
)
from dagster._core.events import DagsterEventType
from openlineage.client import OpenLineageClient
from openlineage.client.event_v2 import InputDataset, Job, OutputDataset, Run, RunEvent, RunState
from openlineage.client.facet_v2 import (
    column_lineage_dataset,
    job_type_job,
    output_statistics_output_dataset,
    schema_dataset,
)
from openlineage.client.transport.http import HttpConfig, HttpTransport

from pluginlake.core.ducklake.io_manager import asset_key_to_table_ref
from pluginlake.core.lineage.config import LineageSettings
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

PRODUCER = "https://github.com/plugin-healthcare/pluginlake"


def dataset_name(asset_key: AssetKey) -> str:
    """Return the OpenLineage dataset name for an asset: its DuckLake table reference."""
    return asset_key_to_table_ref(list(asset_key.path))


def build_job_facets(kinds: AbstractSet[str]) -> dict:
    """Build the ``jobType`` facet from an asset's Dagster kind tags.

    Args:
        kinds: The asset's ``kinds`` (e.g. ``{"polars"}`` or ``{"dbt", "duckdb"}``).

    Returns:
        Job facets keyed by facet name.
    """
    if "dbt" in kinds:
        integration, job_type = "DBT", "MODEL"
    elif "polars" in kinds:
        integration, job_type = "DAGSTER", "POLARS"
    else:
        integration, job_type = "DAGSTER", "ASSET"
    return {
        "jobType": job_type_job.JobTypeJobFacet(
            processingType="BATCH",
            integration=integration,
            jobType=job_type,
        ),
    }


def build_dataset_facets(metadata: Mapping[str, MetadataValue], dataset_namespace: str) -> dict:
    """Translate schema and column-lineage metadata into OpenLineage dataset facets.

    Args:
        metadata: Materialization metadata of the asset.
        dataset_namespace: OpenLineage namespace of the input datasets in column lineage.

    Returns:
        Dataset facets keyed by facet name; empty when no supported metadata is present.
    """
    facets: dict = {}
    schema = metadata.get("dagster/column_schema")
    if isinstance(schema, TableSchemaMetadataValue):
        facets["schema"] = schema_dataset.SchemaDatasetFacet(
            fields=[
                schema_dataset.SchemaDatasetFacetFields(name=column.name, type=column.type)
                for column in schema.value.columns
            ],
        )
    lineage = metadata.get("dagster/column_lineage")
    if isinstance(lineage, TableColumnLineageMetadataValue):
        fields = {
            output_column: column_lineage_dataset.Fields(
                inputFields=[
                    column_lineage_dataset.InputField(
                        namespace=dataset_namespace,
                        name=dataset_name(dep.asset_key),
                        field=dep.column_name,
                    )
                    for dep in deps
                ],
            )
            for output_column, deps in lineage.value.deps_by_column.items()
        }
        if fields:
            facets["columnLineage"] = column_lineage_dataset.ColumnLineageDatasetFacet(fields=fields)
    return facets


def build_output_facets(metadata: Mapping[str, MetadataValue]) -> dict:
    """Translate the ``dagster/row_count`` metadata into the ``outputStatistics`` facet."""
    row_count = metadata.get("dagster/row_count")
    if not isinstance(row_count, IntMetadataValue) or row_count.value is None:
        return {}
    return {
        "outputStatistics": output_statistics_output_dataset.OutputStatisticsOutputDatasetFacet(
            rowCount=row_count.value,
        ),
    }


def build_run_events(
    dagster_run: DagsterRun,
    instance: DagsterInstance,
    repository_def: RepositoryDefinition,
    settings: LineageSettings,
) -> list[RunEvent]:
    """Build one ``COMPLETE`` RunEvent per asset materialized in a Dagster run.

    Each asset becomes an OpenLineage job; its upstream assets are the inputs and
    its own DuckLake table is the output.

    Args:
        dagster_run: The completed Dagster run.
        instance: The Dagster instance to read materialization events from.
        repository_def: Provides each asset's upstream dependencies and kinds.
        settings: Lineage settings (namespaces).

    Returns:
        The OpenLineage events, in materialization order.
    """
    asset_graph = repository_def.asset_graph
    records = instance.get_records_for_run(
        run_id=dagster_run.run_id,
        of_type=DagsterEventType.ASSET_MATERIALIZATION,
    ).records

    events: list[RunEvent] = []
    for record in records:
        asset_key = record.asset_key
        materialization = record.asset_materialization
        if asset_key is None or materialization is None:
            logger.warning("Skipping materialization record without asset key in run %s.", dagster_run.run_id)
            continue
        metadata = materialization.metadata
        in_graph = asset_graph.has(asset_key)
        kinds = asset_graph.get(asset_key).kinds if in_graph else set()
        parents = asset_graph.get(asset_key).parent_keys if in_graph else set()

        inputs = [
            InputDataset(namespace=settings.dataset_namespace, name=dataset_name(parent))
            for parent in sorted(parents, key=lambda key: key.to_user_string())
        ]
        outputs = [
            OutputDataset(
                namespace=settings.dataset_namespace,
                name=dataset_name(asset_key),
                facets=build_dataset_facets(metadata, settings.dataset_namespace),
                outputFacets=build_output_facets(metadata),
            ),
        ]
        # Deterministic per (run, asset), so re-sending an event updates the same OpenLineage run.
        run_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{dagster_run.run_id}:{asset_key.to_user_string()}")
        events.append(
            RunEvent(
                eventType=RunState.COMPLETE,
                eventTime=datetime.fromtimestamp(record.timestamp, tz=UTC).isoformat(),
                run=Run(runId=str(run_id)),
                job=Job(
                    namespace=settings.job_namespace,
                    name=asset_key.to_user_string(),
                    facets=build_job_facets(kinds),
                ),
                producer=PRODUCER,
                inputs=inputs,
                outputs=outputs,
            ),
        )
    return events


def create_client(settings: LineageSettings) -> OpenLineageClient:
    """Create an OpenLineage HTTP client for the configured backend.

    Raises:
        ValueError: If no backend URL is configured.
    """
    if not settings.url:
        msg = "OPENLINEAGE_URL is not set."
        raise ValueError(msg)
    config = HttpConfig(
        url=settings.url,
        endpoint=settings.endpoint,
        timeout=settings.timeout,
        retry={
            "total": settings.retries,
            "read": settings.retries,
            "connect": settings.retries,
            "backoff_factor": 0.3,
            "status_forcelist": [500, 502, 503, 504],
            "allowed_methods": ["HEAD", "POST"],
        },
    )
    return OpenLineageClient(transport=HttpTransport(config))


def emit_run_events(client: OpenLineageClient, events: Sequence[RunEvent]) -> int:
    """Send events to the OpenLineage backend, logging warnings instead of raising.

    Lineage is best-effort and runs after the Dagster run has finished, so a
    failing backend never fails a run. When the backend is unreachable the
    remaining events are skipped, because they would fail the same way; other
    errors (e.g. a rejected event) only skip that event.

    Args:
        client: The OpenLineage client.
        events: The events to send.

    Returns:
        The number of events sent successfully.
    """
    sent = 0
    for index, event in enumerate(events):
        try:
            client.emit(event)
        except (requests.ConnectionError, requests.Timeout) as exc:
            logger.warning(
                "OpenLineage backend unreachable, skipping %d lineage event(s): %s",
                len(events) - index,
                exc,
            )
            break
        except Exception as exc:  # noqa: BLE001 -- lineage must never fail the sensor
            logger.warning("Failed to emit OpenLineage event for job %s: %s", event.job.name, exc)
            continue
        sent += 1
    logger.info("Emitted %d of %d OpenLineage events.", sent, len(events))
    return sent
