"""Flow B: /api/signup DELIBERATELY distinguishes new vs. registered email.

This is an INTENTIONAL reversal of the old non-enumeration design — the
product owner chose clarity over enumeration-resistance. A NEW email yields
``202 confirm_email_sent`` (account created, verification email sent); an
EXISTING email (verified OR unverified, not distinguished) yields
``409 email_exists`` with NO account created and NO email of any kind sent.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _enable_signups(
    http_client: AsyncClient, super_admin_id: str, make_jwt: Callable[..., str]
) -> str:
    """Returns the admin bearer token used to flip the gate; the caller is
    responsible for restoring the original setting."""
    from uuid import UUID

    token = make_jwt(sub=UUID(super_admin_id))
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    return token


async def _disable_signups(http_client: AsyncClient, token: str) -> None:
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": False},
    )


async def test_new_and_existing_email_yield_distinct_responses(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of Flow B: a new email is 202, an existing email is 409."""
    token = await _enable_signups(http_client, str(existing_super_admin.id), make_jwt)
    mock_supabase_admin.auth.sign_up.return_value = MagicMock(
        user=MagicMock(id="00000000-0000-0000-0000-000000000901")
    )

    exists_for: set[str] = {"taken-flowb@example.com"}

    async def _lookup(_db: object, email: str) -> tuple[bool, bool]:
        return (email in exists_for, False)

    monkeypatch.setattr("xtrusio_api.services.signup.lookup_auth_user", _lookup)
    try:
        r_new = await http_client.post(
            "/api/signup",
            json={"email": "new-flowb@example.com", "password": "Password1!"},
        )
        r_existing = await http_client.post(
            "/api/signup",
            json={"email": "taken-flowb@example.com", "password": "Password1!"},
        )
        # New email → account created + verification sent.
        assert r_new.status_code == 202
        assert r_new.json() == {"state": "confirm_email_sent"}
        # Existing email → 409, no account, no email.
        assert r_existing.status_code == 409
        assert r_existing.json()["detail"] == "email_exists"
        # Only the NEW email reached sign_up; the existing one sent nothing.
        mock_supabase_admin.auth.sign_up.assert_called_once()
        mock_supabase_admin.auth.admin.create_user.assert_not_called()
    finally:
        await _disable_signups(http_client, token)


async def test_existing_verified_and_unverified_are_indistinguishable(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flow B does NOT distinguish a verified vs. unverified existing account —
    both return the identical 409 ``email_exists`` (so the UI can't tell which
    is which, and neither triggers any email)."""
    token = await _enable_signups(http_client, str(existing_super_admin.id), make_jwt)
    try:
        for confirmed in (True, False):

            async def _exists(_db: object, _email: str, _c: bool = confirmed) -> tuple[bool, bool]:
                return (True, _c)

            monkeypatch.setattr("xtrusio_api.services.signup.lookup_auth_user", _exists)
            r = await http_client.post(
                "/api/signup",
                json={"email": "dup-flowb@example.com", "password": "Password1!"},
            )
            assert r.status_code == 409
            assert r.json()["detail"] == "email_exists"
        mock_supabase_admin.auth.sign_up.assert_not_called()
        mock_supabase_admin.auth.resend.assert_not_called()
        mock_supabase_admin.auth.reset_password_email.assert_not_called()
    finally:
        await _disable_signups(http_client, token)
