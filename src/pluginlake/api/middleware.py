"""Request/response logging middleware."""

import time
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from pluginlake.utils.jsonl_writer import write_query_log
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every incoming request and its response status/duration."""

    def __init__(self, app, query_log_dir: Path | None = None) -> None:  # noqa: ANN001 — Starlette base class types `app` as ASGIApp internally
        """Initialise with optional JSONL query log directory."""
        super().__init__(app)
        self._query_log_dir = query_log_dir

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process and log the request/response cycle."""
        start = time.perf_counter()
        method = request.method
        path = request.url.path

        logger.info("Request  %s %s", method, path)

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Response %s %s -> %s (%.1fms)",
            method,
            path,
            response.status_code,
            duration_ms,
        )

        if self._query_log_dir is not None:
            write_query_log(
                self._query_log_dir,
                method=method,
                path=path,
                query_params=str(request.query_params),
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )

        return response
