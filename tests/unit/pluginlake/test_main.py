"""Tests for pluginlake FastAPI entry point."""

from http import HTTPStatus

from starlette.testclient import TestClient

from pluginlake.__main__ import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok():
    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ready"}
