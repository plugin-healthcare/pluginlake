"""FastAPI application factory and configuration.

Creates the pluginlake FastAPI application with middleware, routers,
exception handlers, and authentication placeholders.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pluginlake.api.exceptions import register_exception_handlers
from pluginlake.api.middleware import RequestLoggingMiddleware
from pluginlake.api.routers import assets, catalog, fhir, health, ingest, omop, omop_statistics
from pluginlake.config import LogSettings, Settings
from pluginlake.core.config import DuckLakeSettings
from pluginlake.core.ducklake.setup import ensure_database
from pluginlake.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: setup logging and DuckLake database on startup."""
    settings = Settings()
    setup_logging(settings.effective_log_level)
    logger.info("pluginlake API starting")

    ducklake_settings = DuckLakeSettings()  # type: ignore[missing-argument]
    ensure_database(ducklake_settings)

    yield
    logger.info("pluginlake API shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Returns:
        A fully configured FastAPI instance with middleware, routers,
        and exception handlers attached.
    """
    log_settings = LogSettings()
    log_settings.ensure_directories()

    app = FastAPI(
        title="pluginlake",
        description="Central API endpoint for the pluginlake data station.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.log_settings = log_settings

    _add_middleware(app, log_settings)
    _include_routers(app)
    register_exception_handlers(app)

    return app


def _add_middleware(app: FastAPI, log_settings: LogSettings) -> None:
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


def _include_routers(app: FastAPI) -> None:
    """Register all API routers."""
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(omop.router)
    app.include_router(omop_statistics.router)
    app.include_router(catalog.router)
    app.include_router(assets.router)
    app.include_router(fhir.router)
