"""Non-enumeration: /api/signup must not distinguish new vs. registered email.

With the native ``sign_up`` flow, Supabase itself obfuscates an
already-registered email — it returns a 200 with an obfuscated user object
(no error) instead of an "email exists" signal. So the backend contract is
simply: whatever email is submitted, the route calls ``auth.sign_up`` and
returns a BYTE-IDENTICAL 202 ``confirm_email_sent``. There is no per-path
branching, hence no oracle.
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


async def test_new_and_existing_email_yield_identical_response(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    token = await _enable_signups(http_client, str(existing_super_admin.id), make_jwt)
    try:
        # Supabase ``sign_up`` returns 200 with an obfuscated user for BOTH a
        # brand-new and an already-registered email — the backend can't tell
        # them apart, which is the whole point.
        mock_supabase_admin.auth.sign_up.return_value = MagicMock(
            user=MagicMock(id="00000000-0000-0000-0000-000000000901")
        )
        r1 = await http_client.post(
            "/api/signup",
            json={"email": "new-no-enum@example.com", "password": "Password1!"},
        )
        r2 = await http_client.post(
            "/api/signup",
            json={"email": "taken-no-enum@example.com", "password": "Password1!"},
        )
        # CRITICAL: responses are indistinguishable.
        assert r1.status_code == r2.status_code == 202
        assert r1.json() == r2.json() == {"state": "confirm_email_sent"}
        # Both paths take the SAME code path: native sign_up, no admin-create.
        assert mock_supabase_admin.auth.sign_up.call_count == 2
        mock_supabase_admin.auth.admin.create_user.assert_not_called()
    finally:
        await _disable_signups(http_client, token)


async def test_existing_email_does_not_leak_via_field_presence(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    """A tighter assertion: not just status + body equality, but no
    fingerprintable field set across the two submissions."""
    token = await _enable_signups(http_client, str(existing_super_admin.id), make_jwt)
    try:
        mock_supabase_admin.auth.sign_up.return_value = MagicMock(
            user=MagicMock(id="00000000-0000-0000-0000-000000000902")
        )
        r1 = await http_client.post(
            "/api/signup",
            json={"email": "fp-new@example.com", "password": "Password1!"},
        )
        r2 = await http_client.post(
            "/api/signup",
            json={"email": "fp-taken@example.com", "password": "Password1!"},
        )
        # Same keyset, same value, exactly.
        assert set(r1.json().keys()) == set(r2.json().keys())
        for k in r1.json():
            assert r1.json()[k] == r2.json()[k], f"field '{k}' differs across paths"
    finally:
        await _disable_signups(http_client, token)
