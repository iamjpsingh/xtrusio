"""Tests for GET/PUT /api/platform/settings."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser
from xtrusio_api.rbac.grants import grant_role

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_platform_user(db: AsyncSession, *, role_key: str | None) -> tuple:
    """Ephemeral auth.users + platform_users; optional resolver-visible platform
    role grant (the P3b authz source). Never a super_admin."""
    user_id = uuid4()
    email = f"ps-{user_id.hex[:8]}@example.com"
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    db.add(PlatformUser(id=user_id, email=email, role=PlatformRole.EDITOR, is_active=True))
    if role_key is not None:
        await grant_role(db, auth_user_id=user_id, scope="platform", key=role_key)
    await db.commit()
    return user_id, email


async def _drop_platform_user(db: AsyncSession, user_id) -> None:
    await db.execute(text("DELETE FROM user_roles WHERE auth_user_id = :id"), {"id": str(user_id)})
    await db.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
    await db.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
    await db.commit()


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


async def test_put_settings_unprivileged_returns_403_permission_denied(
    http_client: AsyncClient, make_jwt, db_session: AsyncSession
) -> None:
    # P3b authz model: no `platform.settings.manage` grant -> permission_denied.
    user_id, _ = await _seed_platform_user(db_session, role_key=None)
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": True},
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "permission_denied"
    finally:
        await _drop_platform_user(db_session, user_id)


async def test_put_settings_platform_admin_succeeds(
    http_client: AsyncClient, make_jwt, db_session: AsyncSession
) -> None:
    # P3b intentionally CHANGES authz: platform `admin` now holds
    # `platform.settings.manage` (spec matrix) and may edit settings.
    user_id, _ = await _seed_platform_user(db_session, role_key="admin")
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": True},
        )
        assert r.status_code == 200
        assert r.json()["signups_enabled"] is True
    finally:
        await _drop_platform_user(db_session, user_id)


async def test_get_settings_unprivileged_returns_403_permission_denied(
    http_client: AsyncClient, make_jwt, db_session: AsyncSession
) -> None:
    # P3b: GET now requires `platform.settings.read` (previously any auth user).
    user_id, _ = await _seed_platform_user(db_session, role_key=None)
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.get(
            "/api/platform/settings", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "permission_denied"
    finally:
        await _drop_platform_user(db_session, user_id)


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
