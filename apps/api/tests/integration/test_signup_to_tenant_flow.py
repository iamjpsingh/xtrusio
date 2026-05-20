"""End-to-end: super_admin enables signup → anon signs up → simulated email confirm
→ unprovisioned user calls /me → posts /onboarding/tenants → becomes owner."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_signup_to_tenant_flow(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    db_session: AsyncSession,
    mock_supabase_admin: MagicMock,
) -> None:
    # 1. super_admin enables signups.
    sa_token = make_jwt(sub=existing_super_admin.id)
    r = await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"signups_enabled": True},
    )
    assert r.status_code == 200

    # 2. Anon signs up. We pre-allocate the user id so we can simulate the confirm.
    user_id = uuid4()
    mock_supabase_admin.auth.admin.create_user.return_value = MagicMock(
        user=MagicMock(id=str(user_id))
    )
    email = f"e2e-{user_id.hex[:8]}@example.com"
    r = await http_client.post(
        "/api/signup",
        json={"email": email, "password": "Password1!"},
    )
    assert r.status_code == 202

    # 3. Simulate email confirmation: insert into auth.users with a confirmed timestamp.
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    await db_session.commit()

    try:
        # 4. User authenticates, /me reports unprovisioned.
        token = make_jwt(sub=user_id)
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        me = r.json()
        assert me["platform"] is None
        assert me["tenants"] == []

        # 5. Onboarding.
        r = await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json={"workspace_name": "End to End Co"},
        )
        assert r.status_code == 201
        assert r.json()["tenant"]["role"] == "owner"

        # 6. /me now shows them as tenant owner.
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        body = r.json()
        assert len(body["tenants"]) == 1
        assert body["tenants"][0]["role"] == "owner"
    finally:
        # Cleanup: child rows first, then auth.users.
        await db_session.execute(
            text("DELETE FROM tenant_memberships WHERE user_id = :id"),
            {"id": str(user_id)},
        )
        await db_session.execute(
            text("DELETE FROM tenants WHERE created_by = :id"),
            {"id": str(user_id)},
        )
        await db_session.execute(
            text("DELETE FROM auth.users WHERE id = :id"),
            {"id": str(user_id)},
        )
        # Reset signup toggle.
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {sa_token}"},
            json={"signups_enabled": False},
        )
        await db_session.commit()
