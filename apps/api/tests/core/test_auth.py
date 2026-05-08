"""Unit tests for JWT middleware."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient

from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_missing_token_returns_401(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/me")
    assert res.status_code == 401


async def test_malformed_token_returns_401(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


async def test_expired_token_returns_401(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt(sub=uuid4(), expired=True)
    res = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


async def test_unprovisioned_user_returns_401(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Valid JWT but no platform_users row for that sub."""
    token = make_jwt(sub=uuid4())
    res = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


async def test_super_admin_returns_200(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    super_admin_user: PlatformUser,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    res = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == super_admin_user.email
    assert body["role"] == "super_admin"
