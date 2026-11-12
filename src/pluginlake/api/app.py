"""FastAPI application factory and configuration.

Creates the pluginlake FastAPI application with middleware, routers,
exception handlers, and authentication placeholders.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pluginlake import __version__
from pluginlake.api.config import MetricsSettings
from pluginlake.api.exceptions import register_exception_handlers
from pluginlake.api.metrics import PrometheusMiddleware, start_metrics_server, stop_metrics_server
from pluginlake.api.middleware import RequestLoggingMiddleware
from pluginlake.api.routers import (
    assets,
    catalog,
    health,
    hub,
    ingest,
)
from pluginlake.config import LogSettings, Settings
from pluginlake.core.config import DuckLakeSettings
from pluginlake.core.ducklake.setup import close_shared_connection, ensure_database
from pluginlake.plugins.discovery import discover_manifests, load_router
from pluginlake.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: setup logging, DuckLake database and metrics server."""
    settings = Settings()
    setup_logging(settings.effective_log_level)
    logger.info("pluginlake API starting")

    ducklake_settings = DuckLakeSettings()  # type: ignore[missing-argument]
    ensure_database(ducklake_settings)

    metrics_settings: MetricsSettings = app.state.metrics_settings
    metrics_server = start_metrics_server(metrics_settings) if metrics_settings.enabled else None

    yield
    close_shared_connection()
    if metrics_server is not None:
        stop_metrics_server(metrics_server)
    logger.info("pluginlake API shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Returns:
        A fully configured FastAPI instance with middleware, routers,
        and exception handlers attached.
    """
    log_settings = LogSettings()
    log_settings.ensure_directories()
    metrics_settings = MetricsSettings()

    app = FastAPI(
        title="pluginlake",
        description="Central API endpoint for the pluginlake data station.",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.log_settings = log_settings
    app.state.metrics_settings = metrics_settings

    _add_middleware(app, log_settings, metrics_settings)
    _include_routers(app)
    register_exception_handlers(app)

    return app


def _add_middleware(app: FastAPI, log_settings: LogSettings, metrics_settings: MetricsSettings) -> None:
    """Attach middleware to the application."""
    app.add_middleware(
        CORSMiddleware,  # type: ignore[invalid-argument-type]
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RequestLoggingMiddleware,  # type: ignore[invalid-argument-type]
        query_log_dir=log_settings.query_log_dir,
    )
    if metrics_settings.enabled:
        # Added last so it is the outermost middleware and also times the others.
        app.add_middleware(PrometheusMiddleware)  # type: ignore[invalid-argument-type]


def _include_routers(app: FastAPI) -> None:
    """Register API routers.

    Core exposes the uniform routers directly. Project-specific routers are
    contributed declaratively through each project's manifest and mounted
    uniformly, so no project code is imported here (ADR-009).
    """
    app.include_router(health.router)
    app.include_router(hub.router)
    app.include_router(ingest.router)
    app.include_router(catalog.router)
    app.include_router(assets.router)

    for manifest in discover_manifests():
        for spec in manifest.routers:
            app.include_router(load_router(spec))
