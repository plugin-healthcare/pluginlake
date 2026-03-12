"""HTTP client for the pluginlake FastAPI.

Thin wrapper around httpx that handles authentication, timeouts,
and error mapping. No pluginlake package imports.
"""

import logging
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


class ApiError(Exception):
    """Raised when an API call fails."""

    def __init__(self, status_code: int, detail: str) -> None:
        """Initialise with HTTP status code and error detail."""
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class ApiClient:
    """Synchronous HTTP client for a single pluginlake instance."""

    def __init__(
        self,
        base_url: str = _settings.api_url,
        timeout: float = _settings.api_timeout,
        api_key: str | None = _settings.api_key,
    ) -> None:
        """Create a client targeting the pluginlake API."""
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key
        self._client = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)

    # --- Health ---------------------------------------------------------------

    def health(self) -> dict[str, str]:
        """Check API liveness."""
        return self._get("/health")

    def ready(self) -> dict[str, str]:
        """Check API readiness."""
        return self._get("/ready")

    # --- Catalog --------------------------------------------------------------

    def get_catalog_schemas(self) -> list[dict[str, Any]]:
        """List DuckLake schemas."""
        return self._get("/api/v1/catalog/schemas")

    def get_catalog_tables(self, schema: str | None = None) -> list[dict[str, Any]]:
        """List DuckLake tables, optionally filtered by schema."""
        params = {"schema": schema} if schema else {}
        return self._get("/api/v1/catalog/tables", params=params)

    def get_catalog_columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        """List columns for a specific DuckLake table."""
        return self._get("/api/v1/catalog/columns", params={"schema": schema, "table": table})

    # --- Assets ---------------------------------------------------------------

    def get_assets(self) -> list[dict[str, Any]]:
        """List Dagster assets with materialization status."""
        return self._get("/api/v1/assets")

    # --- OMOP Statistics ------------------------------------------------------

    def get_omop_statistics(self) -> dict[str, Any]:
        """Get aggregated OMOP statistics."""
        return self._get("/api/v1/omop/statistics")

    # --- Ingestion ------------------------------------------------------------

    def get_ingestion_info(self) -> dict[str, Any]:
        """Get ingestion endpoint configuration."""
        return self._get("/api/v1/ingest/info")

    def get_ingestion_runs(self) -> list[dict[str, Any]]:
        """Get recent ingestion run history."""
        return self._get("/api/v1/runs")

    def upload_file(self, file_bytes: bytes, filename: str, dataset: str) -> dict[str, Any]:
        """Upload a file for ingestion."""
        return self._post(
            "/api/v1/ingest",
            files={"file": (filename, file_bytes)},
            data={"dataset": dataset},
        )

    def upload_omop_csv(self, file_bytes: bytes, filename: str, table_name: str) -> dict[str, Any]:
        """Upload an OMOP CSV file."""
        return self._post(
            f"/api/v1/omop/{table_name}/csv",
            files={"file": (filename, file_bytes)},
        )

    # --- HTTP helpers ---------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Perform a GET request and return parsed JSON."""
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            logger.warning("API error: %s %s → %s", exc.request.method, exc.request.url, detail)
            raise ApiError(exc.response.status_code, detail) from exc
        except httpx.RequestError as exc:
            logger.exception("Connection error")
            raise ApiError(0, f"Connection failed: {exc}") from exc
        return response.json()

    def _post(
        self,
        path: str,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform a POST request and return parsed JSON."""
        try:
            response = self._client.post(path, files=files, data=data, json=json_body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            logger.warning("API error: %s %s → %s", exc.request.method, exc.request.url, detail)
            raise ApiError(exc.response.status_code, detail) from exc
        except httpx.RequestError as exc:
            logger.exception("Connection error")
            raise ApiError(0, f"Connection failed: {exc}") from exc
        return response.json()
