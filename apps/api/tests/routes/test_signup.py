"""Tests for /api/signup and /api/signup-status."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from gotrue.errors import AuthApiError
from httpx import AsyncClient
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_signup_status_default_false(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/signup-status")
    assert r.status_code == 200
    assert r.json() == {"signups_enabled": False}


async def test_signup_status_served_at_public_path(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/signup-status")
    assert r.status_code == 200
    assert "signups_enabled" in r.json()


async def test_old_platform_signup_status_path_is_gone(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/platform/signup-status")
    assert r.status_code == 404


async def test_signup_disabled_returns_403(
    http_client: AsyncClient, mock_supabase_admin: MagicMock
) -> None:
    r = await http_client.post(
        "/api/signup", json={"email": "anon@example.com", "password": "Password1!"}
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "signups_disabled"
    mock_supabase_admin.auth.admin.create_user.assert_not_called()


async def test_signup_invalid_email_returns_422(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    try:
        r = await http_client.post(
            "/api/signup", json={"email": "not-an-email", "password": "Password1!"}
        )
        assert r.status_code == 422
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )


async def test_signup_happy_path_calls_supabase(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    mock_supabase_admin.auth.admin.create_user.return_value = MagicMock(
        user=MagicMock(id="00000000-0000-0000-0000-000000000999")
    )
    try:
        r = await http_client.post(
            "/api/signup",
            json={"email": "newuser@example.com", "password": "Password1!"},
        )
        assert r.status_code == 202
        assert r.json() == {"state": "confirm_email_sent"}
        mock_supabase_admin.auth.admin.create_user.assert_called_once()
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )


async def test_signup_email_taken_returns_409(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    mock_supabase_admin.auth.admin.create_user.side_effect = AuthApiError(
        "email already registered", 422, "email_exists"
    )
    try:
        r = await http_client.post(
            "/api/signup", json={"email": "taken@example.com", "password": "Password1!"}
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "email_taken"
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )
