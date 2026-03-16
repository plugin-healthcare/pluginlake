"""Dagster asset and run endpoints.

- ``GET /api/v1/assets`` — list Dagster assets with materialization status
- ``GET /api/v1/runs``   — list recent Dagster runs
"""

from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter

from pluginlake.api.config import IngestionSettings
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["assets"])

_ASSETS_QUERY = """
query AssetsQuery {
  assetsOrError {
    __typename
    ... on AssetConnection {
      nodes {
        key { path }
        definition {
          description
          groupName
          metadataEntries {
            __typename
            label
            description
            ... on TableSchemaMetadataEntry {
              schema {
                columns {
                  name
                  type
                  description
                  constraints { other }
                }
              }
            }
          }
        }
        assetMaterializations(limit: 1) {
          runId
          timestamp
          metadataEntries {
            __typename
            label
            description
            ... on TableSchemaMetadataEntry {
              schema {
                columns {
                  name
                  type
                  description
                  constraints { other }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

_RUNS_QUERY = """
query RunsQuery {
  runsOrError(limit: 20) {
    __typename
    ... on Runs {
      results {
        runId
        jobName
        status
        startTime
        endTime
      }
    }
  }
}
"""

_RUN_BY_ID_QUERY = """
query RunById($runId: ID!) {
  runOrError(runId: $runId) {
    __typename
    ... on Run {
      runId
      jobName
      status
      startTime
      endTime
    }
    ... on RunNotFoundError { message }
  }
}
"""


def _graphql_url() -> str:
    settings = IngestionSettings()
    return f"{settings.dagster_webserver_url.rstrip('/')}/graphql"


def _query_dagster(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against the Dagster webserver."""
    try:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        response = httpx.post(_graphql_url(), json=payload, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        logger.exception("Failed to query Dagster GraphQL")
        return {}


def _extract_columns(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract column metadata from Dagster TableSchemaMetadataEntry entries."""
    for entry in entries:
        if entry.get("__typename") == "TableSchemaMetadataEntry":
            schema = entry.get("schema") or {}
            return [
                {
                    "name": col.get("name", ""),
                    "type": col.get("type", ""),
                    "description": col.get("description", ""),
                }
                for col in schema.get("columns", [])
            ]
    return []


@router.get(
    "/assets",
    summary="List Dagster assets",
    description="Returns Dagster assets with their latest materialization status and column metadata.",
)
def list_assets() -> list[dict[str, Any]]:
    """List Dagster assets with materialization status and column info."""
    data = _query_dagster(_ASSETS_QUERY)
    assets_or_error = data.get("data", {}).get("assetsOrError", {})

    if assets_or_error.get("__typename") != "AssetConnection":
        return []

    result = []
    for node in assets_or_error.get("nodes", []):
        key_path = node.get("key", {}).get("path", [])
        definition = node.get("definition") or {}
        materializations = node.get("assetMaterializations", [])
        latest = materializations[0] if materializations else None

        last_materialized = None
        if latest and latest.get("timestamp"):
            last_materialized = datetime.fromtimestamp(float(latest["timestamp"]) / 1000, tz=UTC).isoformat()

        # Column metadata: prefer materialization entries, fall back to definition
        columns: list[dict[str, str]] = []
        if latest:
            columns = _extract_columns(latest.get("metadataEntries", []))
        if not columns:
            columns = _extract_columns(definition.get("metadataEntries", []))

        result.append(
            {
                "key": "/".join(key_path),
                "group": definition.get("groupName", ""),
                "description": definition.get("description", ""),
                "last_materialized": last_materialized,
                "last_run_id": latest.get("runId") if latest else None,
                "columns": columns,
            }
        )

    return result


@router.get(
    "/runs",
    summary="List recent Dagster runs",
    description="Returns the most recent Dagster pipeline runs.",
)
def list_runs() -> list[dict[str, Any]]:
    """List recent Dagster runs."""
    data = _query_dagster(_RUNS_QUERY)
    runs_or_error = data.get("data", {}).get("runsOrError", {})

    if runs_or_error.get("__typename") != "Runs":
        return []

    return [
        {
            "run_id": run.get("runId"),
            "job_name": run.get("jobName"),
            "status": run.get("status"),
            "start_time": run.get("startTime"),
            "end_time": run.get("endTime"),
        }
        for run in runs_or_error.get("results", [])
    ]


@router.get(
    "/runs/{run_id}",
    summary="Get a single Dagster run",
    description="Returns the status of a specific Dagster pipeline run.",
)
def get_run(run_id: str) -> dict[str, Any]:
    """Get the status of a single Dagster run by ID."""
    data = _query_dagster(_RUN_BY_ID_QUERY, variables={"runId": run_id})
    run_or_error = data.get("data", {}).get("runOrError", {})

    if run_or_error.get("__typename") != "Run":
        return {"run_id": run_id, "status": "NOT_FOUND"}

    return {
        "run_id": run_or_error.get("runId"),
        "job_name": run_or_error.get("jobName"),
        "status": run_or_error.get("status"),
        "start_time": run_or_error.get("startTime"),
        "end_time": run_or_error.get("endTime"),
    }
