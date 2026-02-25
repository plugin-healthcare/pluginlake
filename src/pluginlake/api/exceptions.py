"""Global exception handlers for the FastAPI application."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


class PluginLakeError(Exception):
    """Base exception for pluginlake domain errors.

    Args:
        detail: Human-readable error description.
        status_code: HTTP status code to return.
    """

    def __init__(
        self,
        detail: str = "An unexpected error occurred.",
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
    ) -> None:
        """Initialise with a detail message and HTTP status code."""
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app.

    Args:
        app: The FastAPI application instance.
    """

    @app.exception_handler(PluginLakeError)
    async def _handle_pluginlake_error(_request: Request, exc: PluginLakeError) -> JSONResponse:
        logger.warning("Domain error: %s (status=%s)", exc.detail, exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(ValidationError)
    async def _handle_validation_error(_request: Request, exc: ValidationError) -> JSONResponse:
        logger.warning("Validation error: %s", exc.error_count())
        return JSONResponse(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )
