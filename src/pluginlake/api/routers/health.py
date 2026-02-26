"""Health and readiness endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check — returns 200 if the service is running."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict[str, str]:
    """Readiness check — returns 200 when the service can accept traffic.

    Extend this to verify downstream dependencies (database, storage, etc.).
    """
    return {"status": "ready"}
