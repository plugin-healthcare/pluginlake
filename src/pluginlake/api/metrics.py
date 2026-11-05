"""Prometheus metrics for the pluginlake API.

Request count, latency, in-flight requests and unhandled exceptions are recorded
by :class:`PrometheusMiddleware` and served by a separate internal HTTP server
(:func:`start_metrics_server`), so ``/metrics`` is never reachable through the
public API port.

Label values are bounded by design: ``route`` is the matched route template
(e.g. ``/assets/{asset_id}``, never the raw path), ``method`` is limited to the
standard HTTP methods and ``status`` is the numeric response code. User input
and patient data therefore never end up in a metric.
"""

import time
from wsgiref.simple_server import WSGIServer

from prometheus_client import (
    GC_COLLECTOR,
    PLATFORM_COLLECTOR,
    PROCESS_COLLECTOR,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pluginlake.api.config import MetricsSettings
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

UNMATCHED_ROUTE = "unmatched"
OTHER_METHOD = "OTHER"
_KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})

REGISTRY = CollectorRegistry()
for _collector in (PROCESS_COLLECTOR, PLATFORM_COLLECTOR, GC_COLLECTOR):
    REGISTRY.register(_collector)

REQUESTS = Counter(
    "pluginlake_http_requests",
    "HTTP requests handled by the pluginlake API.",
    ["method", "route", "status"],
    registry=REGISTRY,
)
REQUEST_DURATION = Histogram(
    "pluginlake_http_request_duration_seconds",
    "HTTP request latency of the pluginlake API in seconds.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)
REQUESTS_IN_PROGRESS = Gauge(
    "pluginlake_http_requests_in_progress",
    "HTTP requests currently being handled by the pluginlake API.",
    ["method"],
    registry=REGISTRY,
)
EXCEPTIONS = Counter(
    "pluginlake_http_exceptions",
    "Unhandled exceptions raised while handling HTTP requests.",
    ["method", "route", "exception"],
    registry=REGISTRY,
)


def normalize_method(method: str) -> str:
    """Map an HTTP method to a bounded label value."""
    upper = method.upper()
    return upper if upper in _KNOWN_METHODS else OTHER_METHOD


def route_template(scope: Scope) -> str:
    """Return the matched route template for a request scope.

    Requests that did not match a route (404s, scanners) all share one label
    value, so arbitrary request paths never become label values.
    """
    route = scope.get("route")
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return UNMATCHED_ROUTE


class PrometheusMiddleware:
    """ASGI middleware that records request metrics for every HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the downstream ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Record count, latency and exceptions of an HTTP request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = normalize_method(scope["method"])
        # An exception before the response starts ends up as a 500 response.
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        in_progress = REQUESTS_IN_PROGRESS.labels(method)
        in_progress.inc()
        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            EXCEPTIONS.labels(method, route_template(scope), type(exc).__name__).inc()
            raise
        finally:
            route = route_template(scope)
            REQUEST_DURATION.labels(method, route).observe(time.perf_counter() - start)
            REQUESTS.labels(method, route, str(status_code)).inc()
            in_progress.dec()


def start_metrics_server(settings: MetricsSettings) -> WSGIServer | None:
    """Start the internal HTTP server that serves the metrics in Prometheus format.

    Failing to bind the port must not take the API down, so errors are logged
    and ``None`` is returned.

    Args:
        settings: Metrics settings with the bind address and port.

    Returns:
        The running server, or ``None`` if it could not be started.
    """
    try:
        server, _thread = start_http_server(settings.port, addr=settings.host, registry=REGISTRY)
    except OSError:
        # Error, not warning: Prometheus will report the target down, and with several
        # processes on one port only the first one exports, so this must stand out.
        logger.exception(
            "Could not start metrics server on %s:%d; metrics are not exposed",
            settings.host,
            settings.port,
        )
        return None
    logger.info("Metrics server listening on %s:%d", settings.host, server.server_port)
    return server


def stop_metrics_server(server: WSGIServer) -> None:
    """Stop the internal metrics server and release its port."""
    server.shutdown()
    server.server_close()
    logger.info("Metrics server stopped")
