"""Tests for the Prometheus metrics of the pluginlake API."""

import logging
import urllib.request
from http import HTTPStatus

import pytest
from fastapi import APIRouter, FastAPI
from prometheus_client import generate_latest
from starlette.testclient import TestClient

from pluginlake.api.app import create_app
from pluginlake.api.config import MetricsSettings
from pluginlake.api.metrics import (
    OTHER_METHOD,
    REGISTRY,
    UNMATCHED_ROUTE,
    normalize_method,
    route_template,
    start_metrics_server,
    stop_metrics_server,
)

PATIENT_ID = "patient-1234567"


@pytest.fixture
def app() -> FastAPI:
    app = create_app()
    router = APIRouter()

    @router.get("/records/{record_id}")
    def _record(record_id: str) -> dict:
        return {"id": record_id}

    @router.get("/explode")
    def _explode() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _requests(route: str, status: str) -> float:
    return (
        REGISTRY.get_sample_value("pluginlake_http_requests_total", {"method": "GET", "route": route, "status": status})
        or 0.0
    )


def test_counts_requests_by_route_template(client: TestClient):
    before = _requests("/records/{record_id}", "200")
    client.get(f"/records/{PATIENT_ID}")
    assert _requests("/records/{record_id}", "200") == before + 1


def test_records_latency(client: TestClient):
    labels = {"method": "GET", "route": "/health"}
    before = REGISTRY.get_sample_value("pluginlake_http_request_duration_seconds_count", labels) or 0.0
    client.get("/health")
    assert REGISTRY.get_sample_value("pluginlake_http_request_duration_seconds_count", labels) == before + 1


def test_counts_unhandled_exceptions(client: TestClient):
    labels = {"method": "GET", "route": "/explode", "exception": "RuntimeError"}
    before = REGISTRY.get_sample_value("pluginlake_http_exceptions_total", labels) or 0.0
    resp = client.get("/explode")
    assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert REGISTRY.get_sample_value("pluginlake_http_exceptions_total", labels) == before + 1
    assert _requests("/explode", "500") >= 1


def test_unmatched_paths_share_one_label(client: TestClient):
    before = _requests(UNMATCHED_ROUTE, "404")
    client.get(f"/does-not-exist/{PATIENT_ID}")
    assert _requests(UNMATCHED_ROUTE, "404") == before + 1


def test_no_user_input_in_metrics(client: TestClient):
    client.get(f"/records/{PATIENT_ID}", params={"bsn": "123456789"})
    client.get(f"/unknown/{PATIENT_ID}")
    client.request("BREW", f"/records/{PATIENT_ID}")
    exposition = generate_latest(REGISTRY).decode()
    assert PATIENT_ID not in exposition
    assert "123456789" not in exposition
    assert "BREW" not in exposition


@pytest.mark.parametrize(
    ("method", "expected"),
    [("get", "GET"), ("DELETE", "DELETE"), ("BREW", OTHER_METHOD)],
)
def test_normalize_method(method: str, expected: str):
    assert normalize_method(method) == expected


def test_route_template_without_route():
    assert route_template({"type": "http"}) == UNMATCHED_ROUTE


def test_metrics_not_served_on_api_port(client: TestClient):
    assert client.get("/metrics").status_code == HTTPStatus.NOT_FOUND


def test_metrics_server_serves_prometheus_format():
    server = start_metrics_server(MetricsSettings.model_construct(host="127.0.0.1", port=0))
    assert server is not None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/metrics") as resp:
            body = resp.read().decode()
    finally:
        stop_metrics_server(server)
    assert "# TYPE pluginlake_http_requests_total counter" in body
    assert "process_cpu_seconds_total" in body


def test_metrics_server_port_in_use_is_logged_as_error(caplog: pytest.LogCaptureFixture):
    first = start_metrics_server(MetricsSettings.model_construct(host="127.0.0.1", port=0))
    assert first is not None
    try:
        second = start_metrics_server(MetricsSettings(host="127.0.0.1", port=first.server_port))
    finally:
        stop_metrics_server(first)
    assert second is None
    assert any(r.levelno == logging.ERROR and "Could not start metrics server" in r.message for r in caplog.records)


def test_middleware_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLUGINLAKE_METRICS_ENABLED", "false")
    client = TestClient(create_app())
    before = _requests("/health", "200")
    client.get("/health")
    assert _requests("/health", "200") == before
