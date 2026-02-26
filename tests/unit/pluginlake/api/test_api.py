"""Tests for the pluginlake API layer.

Covers middleware logging, CORS headers, exception handlers,
and auth placeholder behaviour.
"""

import logging
from http import HTTPStatus

import pytest
from fastapi import APIRouter, Depends
from starlette.testclient import TestClient

from pluginlake.api.app import create_app
from pluginlake.api.exceptions import PluginLakeError
from pluginlake.api.security import CurrentUser, User, require_role


@pytest.fixture
def app():
    """Create a fresh app instance for each test."""
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health & readiness
# ---------------------------------------------------------------------------


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == HTTPStatus.OK
    assert resp.json() == {"status": "ok"}


def test_ready_endpoint(client):
    resp = client.get("/ready")
    assert resp.status_code == HTTPStatus.OK
    assert resp.json() == {"status": "ready"}


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------


def test_cors_allows_any_origin(client):
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://example.com"


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------


def test_request_logging_middleware(client, caplog):
    with caplog.at_level(logging.INFO, logger="pluginlake"):
        client.get("/health")

    messages = [r.message for r in caplog.records]
    assert any("Request" in m and "/health" in m for m in messages)
    assert any("Response" in m and "200" in m for m in messages)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


def test_unhandled_exception_returns_500(app, client):
    router = APIRouter()

    @router.get("/fail")
    def _fail():
        msg = "boom"
        raise RuntimeError(msg)

    app.include_router(router)

    resp = client.get("/fail")
    assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert resp.json() == {"detail": "Internal server error."}


def test_domain_error_returns_custom_status(app, client):
    router = APIRouter()

    @router.get("/domain-error")
    def _domain_error():
        raise PluginLakeError(detail="Not found", status_code=HTTPStatus.NOT_FOUND)

    app.include_router(router)

    resp = client.get("/domain-error")
    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json() == {"detail": "Not found"}


# ---------------------------------------------------------------------------
# Auth placeholder — passes through
# ---------------------------------------------------------------------------


def test_auth_placeholder_returns_anonymous_user(app, client):
    router = APIRouter()

    @router.get("/me")
    async def _me(user: CurrentUser) -> dict:
        return {"id": user.id, "name": user.name}

    app.include_router(router)

    resp = client.get("/me")
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    assert data["id"] == "anonymous"
    assert data["name"] == "Anonymous User"


def test_require_role_placeholder_passes(app, client):
    router = APIRouter()

    @router.get("/admin", dependencies=[Depends(require_role("admin"))])
    def _admin():
        return {"access": "granted"}

    app.include_router(router)

    resp = client.get("/admin")
    assert resp.status_code == HTTPStatus.OK
    assert resp.json() == {"access": "granted"}


# ---------------------------------------------------------------------------
# Auth model
# ---------------------------------------------------------------------------


def test_user_defaults():
    user = User()
    assert user.id == "anonymous"
    assert "viewer" in user.roles


def test_user_custom():
    user = User(id="u1", name="Admin", roles={"admin", "viewer"})
    assert user.id == "u1"
    assert "admin" in user.roles
