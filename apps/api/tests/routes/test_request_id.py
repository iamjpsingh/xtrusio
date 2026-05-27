"""PAR-B M13: request-id round-trip + presence on error bodies."""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


async def test_generated_request_id_when_header_absent(http_client: AsyncClient) -> None:
    """No inbound ``X-Request-ID`` → middleware generates a UUIDv4 and
    echoes it on the response."""
    resp = await http_client.get("/health/live")
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None
    assert _UUID_RE.match(rid), f"expected UUID, got {rid!r}"


async def test_inbound_request_id_is_preserved(http_client: AsyncClient) -> None:
    """Operators / proxies may pin the id by passing the header — we honour
    it verbatim and echo it back."""
    pinned = "11111111-2222-3333-4444-555555555555"
    resp = await http_client.get("/health/live", headers={"X-Request-ID": pinned})
    assert resp.headers.get("X-Request-ID") == pinned


async def test_request_id_in_error_body(http_client: AsyncClient) -> None:
    """A 404 — or any error — must carry the request_id in the body so a
    user-reported error can be traced in logs without guesswork."""
    resp = await http_client.get("/api/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert "request_id" in body
    assert body["request_id"] is not None
