"""Zitadel Actions v2 webhook that exposes the project roles of a user as ``groups`` claim.

Zitadel calls this service on the functions ``preuserinfo`` and ``preaccesstoken`` and signs the
request with the signing key of the target. oauth2-proxy needs ``groups`` as a list, while Zitadel
only emits its roles claim as an object.

The service is stateless and fails closed: a missing key, a bad signature or an old timestamp
all produce an error, and the target is configured with ``interruptOnError`` so Zitadel then
refuses to issue the token.
"""

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic_settings import BaseSettings, SettingsConfigDict

from pluginlake.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


class GroupsHookSettings(BaseSettings):
    """Settings for ``python -m pluginlake.deploy.groups_hook``.

    All settings can be overridden via environment variables prefixed with
    ``PLUGINLAKE_GROUPS_HOOK_``.
    """

    model_config = SettingsConfigDict(env_prefix="PLUGINLAKE_GROUPS_HOOK_", extra="ignore")

    host: str = "0.0.0.0"  # noqa: S104  # reachable on the internal edge network only
    port: int = 8000
    signing_key_file: Path = Path("/bootstrap/groups-hook.key")
    tolerance_seconds: int = 300


def parse_signature(header: str) -> tuple[int, str] | None:
    """Parse ``t=<timestamp>,v1=<hex>`` and return the timestamp and signature, or None when malformed."""
    parts = dict(item.partition("=")[::2] for item in header.split(","))
    try:
        return int(parts["t"]), parts["v1"]
    except (KeyError, ValueError):
        return None


def verify_signature(body: bytes, header: str, key: str, tolerance: int, now: float | None = None) -> bool:
    """Check the HMAC-SHA256 signature of a Zitadel webhook call and that it is recent."""
    parsed = parse_signature(header)
    if parsed is None:
        return False
    timestamp, signature = parsed
    if abs((time.time() if now is None else now) - timestamp) > tolerance:
        return False
    expected = hmac.new(key.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def groups_from_payload(payload: dict) -> list[str]:
    """Return the unique role keys of all user grants, in order of first appearance."""
    roles = [role for grant in payload.get("user_grants") or [] for role in grant.get("roles") or []]
    return list(dict.fromkeys(roles))


def create_app(settings: GroupsHookSettings) -> FastAPI:
    """Build the webhook application."""
    app = FastAPI(title="pluginlake groups hook", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/groups")
    async def groups(request: Request, zitadel_signature: Annotated[str, Header()] = "") -> dict:
        if not settings.signing_key_file.is_file() or not (key := settings.signing_key_file.read_text().strip()):
            raise HTTPException(status_code=503, detail="signing key not available")
        body = await request.body()
        if not verify_signature(body, zitadel_signature, key, settings.tolerance_seconds):
            logger.warning("Rejected a call with an invalid or expired signature")
            raise HTTPException(status_code=401, detail="invalid signature")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=400, detail="invalid body") from error
        groups = groups_from_payload(payload)
        logger.info("Returned %d groups for function %s", len(groups), payload.get("function"))
        return {"append_claims": [{"key": "groups", "value": groups}]}

    return app


def main() -> None:
    """Entry point of the ``zitadel-groups-hook`` container."""
    setup_logging()
    settings = GroupsHookSettings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
