"""Tests for the Zitadel groups webhook."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from pluginlake.deploy.groups_hook import GroupsHookSettings, create_app, groups_from_payload, verify_signature

KEY = "secret"
BODY = json.dumps({"user_grants": [{"roles": ["api", "dagster"]}, {"roles": ["dagster"]}]}).encode()


def _sign(body: bytes, timestamp: int | None = None) -> str:
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(KEY.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


@pytest.fixture
def client(tmp_path):
    key_file = tmp_path / "hook.key"
    key_file.write_text(KEY + "\n")
    return TestClient(create_app(GroupsHookSettings(signing_key_file=key_file)))


def test_signed_request_returns_unique_roles_as_groups(client):
    response = client.post("/groups", content=BODY, headers={"zitadel-signature": _sign(BODY)})
    assert response.status_code == 200
    assert response.json() == {"append_claims": [{"key": "groups", "value": ["api", "dagster"]}]}


def test_user_without_grants_gets_empty_groups():
    assert groups_from_payload({}) == []


def test_tampered_body_is_rejected(client):
    response = client.post("/groups", content=BODY + b" ", headers={"zitadel-signature": _sign(BODY)})
    assert response.status_code == 401


def test_missing_or_malformed_signature_is_rejected(client):
    assert client.post("/groups", content=BODY).status_code == 401
    assert client.post("/groups", content=BODY, headers={"zitadel-signature": "garbage"}).status_code == 401


def test_expired_signature_is_rejected():
    assert not verify_signature(BODY, _sign(BODY, 1000), KEY, tolerance=300)


def test_missing_key_fails_closed(tmp_path):
    app = create_app(GroupsHookSettings(signing_key_file=tmp_path / "absent.key"))
    response = TestClient(app).post("/groups", content=BODY, headers={"zitadel-signature": _sign(BODY)})
    assert response.status_code == 503
