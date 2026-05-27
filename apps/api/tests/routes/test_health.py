"""PAR-B L1: /health/live answers without DB; /health/ready hits the DB."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_live_returns_ok(http_client: AsyncClient) -> None:
    resp = await http_client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_ready_returns_ok_when_db_reachable(http_client: AsyncClient) -> None:
    """Happy-path readiness — DB is reachable in the test environment."""
    resp = await http_client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_legacy_health_alias_still_works(http_client: AsyncClient) -> None:
    """The pre-PAR-B ``GET /health`` path is preserved for existing pingers."""
    resp = await http_client.get("/health")
    assert resp.status_code == 200
