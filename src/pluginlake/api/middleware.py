"""Request/response logging middleware."""

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every incoming request and its response status/duration."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process and log the request/response cycle.

        Args:
            request: The incoming HTTP request.
            call_next: Callable that passes the request to the next handler.

        Returns:
            The HTTP response after logging.
        """
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

        return response
