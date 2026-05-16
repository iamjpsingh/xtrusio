"""Tests for GET/PUT /api/platform/settings."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_get_settings_unauthenticated(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/platform/settings")
    assert r.status_code == 401


async def test_get_settings_reflects_stored_values(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt,
    db_session: AsyncSession,
) -> None:
    # Read the live DB row so the assertion is robust to whatever the operator set.
    db_row = (
        await db_session.execute(
            text("SELECT signups_enabled, updated_by FROM platform_settings WHERE id = 1")
        )
    ).first()
    assert db_row is not None, "platform_settings singleton row must exist"
    db_signups_enabled: bool = db_row[0]
    db_updated_by = db_row[1]  # UUID or None

    token = make_jwt(sub=existing_super_admin.id)
    r = await http_client.get(
        "/api/platform/settings", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    body = r.json()
    # Shape check.
    assert "signups_enabled" in body
    assert "updated_by_email" in body
    assert "updated_at" in body
    # Value check: endpoint must faithfully reflect what is stored.
    assert body["signups_enabled"] == db_signups_enabled
    if db_updated_by is None:
        assert body["updated_by_email"] is None
    else:
        assert isinstance(body["updated_by_email"], str) and body["updated_by_email"] != ""


async def test_put_settings_requires_super_admin(
    http_client: AsyncClient, make_jwt, db_session: AsyncSession
) -> None:
    user_id = uuid4()
    email = f"admin-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    db_session.add(PlatformUser(id=user_id, email=email, role=PlatformRole.ADMIN, is_active=True))
    await db_session.commit()

    try:
        token = make_jwt(sub=user_id)
        r = await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": True},
        )
        assert r.status_code == 403
    finally:
        await db_session.execute(
            text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)}
        )
        await db_session.execute(
            text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)}
        )
        await db_session.commit()


async def test_put_settings_happy_path(
    http_client: AsyncClient, existing_super_admin: PlatformUser, make_jwt
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    r = await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["signups_enabled"] is True
    assert body["updated_by_email"] == existing_super_admin.email
    # Restore to default for test isolation.
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": False},
    )
