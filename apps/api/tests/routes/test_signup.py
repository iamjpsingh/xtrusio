"""Tests for /api/signup and /api/signup-status.

Native ``sign_up`` model: signup is hard-gated by ``signups_enabled``
(disabled → 403, no auth user created). When enabled, the route calls the
ANON-key client's ``auth.sign_up`` — which sends the confirmation email and
natively obfuscates an already-registered email (no 409 oracle). The route
ALWAYS returns 202 ``confirm_email_sent`` when enabled.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_signup_status_served_at_public_path(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/signup-status")
    assert r.status_code == 200
    assert "signups_enabled" in r.json()


async def test_old_platform_signup_status_path_is_gone(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/platform/signup-status")
    assert r.status_code == 404


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


async def test_signup_resend_happy_path_returns_202(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    """Gated ON: /signup/resend calls ``auth.resend`` and returns 202."""
    token = make_jwt(sub=existing_super_admin.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    try:
        r = await http_client.post("/api/signup/resend", json={"email": "resend-route@example.com"})
        assert r.status_code == 202
        assert r.json() == {"state": "confirm_email_sent"}
        mock_supabase_admin.auth.resend.assert_called_once()
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )


async def test_signup_resend_already_confirmed_still_returns_202(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    """An already-confirmed email makes GoTrue ``resend`` raise an AuthApiError;
    the endpoint SWALLOWS it and still returns the identical 202 — no oracle."""
    from gotrue.errors import AuthApiError

    token = make_jwt(sub=existing_super_admin.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    mock_supabase_admin.auth.resend.side_effect = AuthApiError(
        "email already confirmed", 422, "user_already_exists"
    )
    try:
        r = await http_client.post(
            "/api/signup/resend", json={"email": "confirmed-route@example.com"}
        )
        assert r.status_code == 202
        assert r.json() == {"state": "confirm_email_sent"}
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )


async def test_signup_resend_transport_failure_returns_502(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    """A ``resend`` transport error surfaces as 502 email_provider_unavailable."""
    import httpx

    token = make_jwt(sub=existing_super_admin.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    mock_supabase_admin.auth.resend.side_effect = httpx.ConnectError("boom")
    try:
        r = await http_client.post("/api/signup/resend", json={"email": "resend-down@example.com"})
        assert r.status_code == 502
        assert r.json()["detail"] == "email_provider_unavailable"
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )


async def test_signup_happy_path_calls_native_sign_up(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    """Gated ON: the route calls ``auth.sign_up`` (native flow) and NEVER
    ``admin.create_user`` — the old admin-create path is gone."""
    token = make_jwt(sub=existing_super_admin.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    mock_supabase_admin.auth.sign_up.return_value = MagicMock(
        user=MagicMock(id="00000000-0000-0000-0000-000000000999")
    )
    try:
        r = await http_client.post(
            "/api/signup",
            json={"email": "newuser@example.com", "password": "Password1!"},
        )
        assert r.status_code == 202
        assert r.json() == {"state": "confirm_email_sent"}
        mock_supabase_admin.auth.sign_up.assert_called_once()
        # The admin-create path is removed: it must NEVER be called from signup.
        mock_supabase_admin.auth.admin.create_user.assert_not_called()
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )
