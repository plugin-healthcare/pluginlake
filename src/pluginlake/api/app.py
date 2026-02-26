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
from pluginlake.api.routers import health
from pluginlake.config import Settings
from pluginlake.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: setup logging on startup."""
    settings = Settings()
    setup_logging(settings.effective_log_level)
    logger.info("pluginlake API starting")
    yield
    logger.info("pluginlake API shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Returns:
        A fully configured FastAPI instance with middleware, routers,
        and exception handlers attached.
    """
    app = FastAPI(
        title="pluginlake",
        description="Central API endpoint for the pluginlake data station.",
        version="0.1.0",
        lifespan=lifespan,
    )

    _add_middleware(app)
    _include_routers(app)
    register_exception_handlers(app)

    return app


def _add_middleware(app: FastAPI) -> None:
    """Attach middleware to the application."""
    app.add_middleware(
        CORSMiddleware,  # type: ignore[invalid-argument-type]
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)  # type: ignore[invalid-argument-type]


def _include_routers(app: FastAPI) -> None:
    """Register all API routers."""
    app.include_router(health.router)
