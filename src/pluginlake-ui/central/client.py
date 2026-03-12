"""HTTP client for remote pluginlake datastation APIs.

Each ApiClient instance targets one datastation. The StationPool
manages connections to all configured datastations with fan-out
and graceful error handling per station.
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
    """Synchronous HTTP client for a single pluginlake datastation."""

    def __init__(
        self,
        base_url: str,
        timeout: float = _settings.station_timeout,
        api_key: str | None = _settings.api_key,
    ) -> None:
        """Create a client targeting *base_url*."""
        self.base_url = base_url
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key
        self._client = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)

    def health(self) -> dict[str, str]:
        """Check API liveness."""
        return self._get("/health")

    def get_omop_statistics(self) -> dict[str, Any]:
        """Get aggregated OMOP statistics."""
        return self._get("/api/v1/omop/statistics")

    def get_assets(self) -> list[dict[str, Any]]:
        """List Dagster assets with materialization status."""
        return self._get("/api/v1/assets")

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
            logger.exception("Connection error to %s", self.base_url)
            raise ApiError(0, f"Connection failed: {exc}") from exc
        return response.json()


class StationPool:
    """Manages connections to all configured datastations.

    Provides fan-out methods that call each station and aggregate results,
    handling partial failures gracefully.
    """

    def __init__(self, urls: list[str] | None = None) -> None:
        """Build a pool from *urls* or the configured station list."""
        urls = urls or _settings.station_urls
        self.clients = {url: ApiClient(base_url=url) for url in urls}

    def health_check_all(self) -> dict[str, dict[str, Any]]:
        """Check health of all stations. Returns {url: {status, error?}}."""
        results: dict[str, dict[str, Any]] = {}
        for url, client in self.clients.items():
            try:
                health = client.health()
                results[url] = {"status": "ok", "response": health}
            except ApiError as exc:
                results[url] = {"status": "unreachable", "error": exc.detail}
        return results

    def fetch_all_statistics(self) -> dict[str, dict[str, Any]]:
        """Fetch OMOP statistics from all stations. Returns {url: stats_or_error}."""
        results: dict[str, dict[str, Any]] = {}
        for url, client in self.clients.items():
            try:
                stats = client.get_omop_statistics()
                results[url] = {"status": "ok", "data": stats}
            except ApiError as exc:
                logger.warning("Failed to fetch stats from %s: %s", url, exc.detail)
                results[url] = {"status": "error", "error": exc.detail}
        return results
