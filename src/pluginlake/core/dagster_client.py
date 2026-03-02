"""Async client for the Dagster GraphQL API.

Provides a lightweight wrapper around Dagster's webserver GraphQL endpoint
to trigger jobs and query run status from the pluginlake API layer.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_LAUNCH_RUN_MUTATION = """
mutation LaunchRun($executionParams: ExecutionParams!) {
  launchRun(executionParams: $executionParams) {
    __typename
    ... on LaunchRunSuccess {
      run {
        runId
        status
      }
    }
    ... on PythonError {
      message
      stack
    }
    ... on InvalidStepError {
      invalidStepKey
    }
    ... on RunConfigValidationInvalid {
      errors {
        message
      }
    }
    ... on PresetNotFoundError {
      message
    }
    ... on ConflictingExecutionParamsError {
      message
    }
    ... on UnauthorizedError {
      message
    }
    ... on RunConflict {
      message
    }
    ... on NoModeProvidedError {
      message
    }
  }
}
"""


class DagsterClientError(Exception):
    """Raised when a Dagster API call fails."""


@dataclass
class DagsterRunResult:
    """Result of a Dagster job launch.

    Attributes:
        run_id: Unique identifier of the launched run.
        status: Initial status of the run (e.g. ``STARTING``).
    """

    run_id: str
    status: str


class DagsterClient:
    """Async client for Dagster's GraphQL API.

    Args:
        webserver_url: Base URL of the Dagster webserver
            (e.g. ``http://localhost:3000``).
        timeout: HTTP request timeout in seconds.
    """

    def __init__(self, webserver_url: str, *, timeout: float = 30.0) -> None:
        """Initialise the client with the Dagster webserver URL."""
        self._graphql_url = f"{webserver_url.rstrip('/')}/graphql"
        self._timeout = timeout

    async def trigger_job(
        self,
        job_name: str,
        *,
        repository_location_name: str = "pluginlake.definitions",
        repository_name: str = "__repository__",
        run_config: dict[str, Any] | None = None,
    ) -> DagsterRunResult:
        """Launch a Dagster job run via the GraphQL API.

        Args:
            job_name: Name of the Dagster job to trigger.
            repository_location_name: Dagster repository location name.
            repository_name: Dagster repository name.
            run_config: Optional run configuration dictionary.

        Returns:
            A DagsterRunResult with the run ID and initial status.

        Raises:
            DagsterClientError: If the launch request fails or Dagster
                returns an error response.
        """
        variables: dict[str, Any] = {
            "executionParams": {
                "selector": {
                    "repositoryLocationName": repository_location_name,
                    "repositoryName": repository_name,
                    "jobName": job_name,
                },
                "runConfigData": run_config or {},
            },
        }

        logger.info("Triggering Dagster job %r", job_name)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._graphql_url,
                    json={"query": _LAUNCH_RUN_MUTATION, "variables": variables},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Failed to connect to Dagster webserver at {self._graphql_url}: {exc}"
            raise DagsterClientError(msg) from exc

        data = response.json()
        return self._parse_launch_response(data)

    def _parse_launch_response(self, data: dict[str, Any]) -> DagsterRunResult:
        """Extract run info from the GraphQL response."""
        result = data.get("data", {}).get("launchRun", {})
        typename = result.get("__typename", "")

        if typename == "LaunchRunSuccess":
            run = result["run"]
            run_id = run["runId"]
            status = run["status"]
            logger.info("Dagster run launched: %s (status=%s)", run_id, status)
            return DagsterRunResult(run_id=run_id, status=status)

        error_msg = result.get("message", "") or str(result.get("errors", "Unknown error"))
        msg = f"Dagster launch failed ({typename}): {error_msg}"
        raise DagsterClientError(msg)
