"""Request/response logging middleware."""

import time
from pathlib import Path

from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pluginlake.utils.jsonl_writer import write_query_log
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware:
    """Log every HTTP request and its response status/duration.

    A pure ASGI middleware: unlike ``BaseHTTPMiddleware`` it does not wrap the
    request and response in extra tasks and streams, and it also logs requests
    that end in an unhandled exception (as status 500).
    """

    def __init__(self, app: ASGIApp, query_log_dir: Path | None = None) -> None:
        """Wrap the downstream app, optionally writing a JSONL query log."""
        self.app = app
        self._query_log_dir = query_log_dir

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process and log the request/response cycle."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = HTTPConnection(scope)
        method = scope["method"]
        path = request.url.path
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        logger.info("Request  %s %s", method, path)
        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info("Response %s %s -> %s (%.1fms)", method, path, status_code, duration_ms)
            if self._query_log_dir is not None:
                write_query_log(
                    self._query_log_dir,
                    method=method,
                    path=path,
                    query_params=str(request.query_params),
                    status_code=status_code,
                    duration_ms=duration_ms,
                    client_ip=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                )
