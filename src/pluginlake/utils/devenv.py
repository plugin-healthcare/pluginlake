"""Dev environment service checks for notebooks and local development."""

import socket
from typing import NamedTuple

import httpx

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 2.0


class ServiceStatus(NamedTuple):
    """Result of a single service connectivity check."""

    name: str
    url: str
    ok: bool
    detail: str


def _check_postgres(host: str = "localhost", port: int = 5432) -> ServiceStatus:
    url = f"{host}:{port}"
    try:
        with socket.create_connection((host, port), timeout=_TIMEOUT):
            logger.debug("PostgreSQL reachable at %s", url)
            return ServiceStatus(name="PostgreSQL", url=url, ok=True, detail="Accepting connections")
    except OSError as exc:
        logger.warning("PostgreSQL unreachable at %s: %s", url, exc)
        return ServiceStatus(name="PostgreSQL", url=url, ok=False, detail=str(exc))


def _check_http(name: str, url: str) -> ServiceStatus:
    try:
        resp = httpx.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        logger.debug("%s reachable at %s", name, url)
        return ServiceStatus(name=name, url=url, ok=True, detail=f"HTTP {resp.status_code}")
    except httpx.HTTPStatusError as exc:
        logger.warning("%s returned error at %s: %s", name, url, exc)
        return ServiceStatus(name=name, url=url, ok=False, detail=f"HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        logger.warning("%s unreachable at %s: %s", name, url, exc)
        return ServiceStatus(name=name, url=url, ok=False, detail=str(exc))


def check_dev_services() -> list[ServiceStatus]:
    """Check PostgreSQL, Dagster, and FastAPI connectivity for the local dev stack."""
    return [
        _check_postgres(),
        _check_http("Dagster", "http://localhost:3000/server_info"),
        _check_http("FastAPI", "http://localhost:8000/health"),
    ]
