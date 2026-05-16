"""Tests for GET /api/me — composite identity response."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_me_unauth_returns_401(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/me")
    assert r.status_code == 401


async def test_me_super_admin(
    http_client: AsyncClient, super_admin_user: PlatformUser, make_jwt
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == super_admin_user.email
    assert body["platform"]["role"] == "super_admin"
    assert body["tenants"] == []
    assert body["pending_invite"] is None


async def test_me_tenant_member(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    user_id = uuid4()
    email = f"member-{user_id.hex[:8]}@example.com"
    slug = f"t-{user_id.hex[:8]}"
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    await db_session.execute(
        text("INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"),
        {"slug": slug, "name": "T", "uid": str(user_id)},
    )
    await db_session.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
            "SELECT id, :uid, 'owner' FROM tenants WHERE slug = :slug"
        ),
        {"uid": str(user_id), "slug": slug},
    )
    await db_session.commit()
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["platform"] is None
        assert len(body["tenants"]) == 1
        assert body["tenants"][0]["role"] == "owner"
        assert body["tenants"][0]["slug"] == slug
        assert body["pending_invite"] is None
    finally:
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
        await db_session.commit()


async def test_me_unprovisioned(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    user_id = uuid4()
    email = f"unprov-{user_id.hex[:8]}@example.com"
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
        token = make_jwt(sub=user_id)
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["platform"] is None
        assert body["tenants"] == []
        assert body["pending_invite"] is None
    finally:
        await db_session.execute(
            text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)}
        )
        await db_session.commit()


async def test_me_with_pending_platform_invite(
    http_client: AsyncClient, super_admin_user, make_jwt, db_session: AsyncSession
) -> None:
    invite_id = uuid4()
    user_id = uuid4()
    email = f"pi-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO platform_invites (id, email, role, invited_by, expires_at) "
            "VALUES (:id, :email, 'admin', :inv, :exp)"
        ),
        {
            "id": str(invite_id),
            "email": email,
            "inv": str(super_admin_user.id),
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
    )
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
        token = make_jwt(
            sub=user_id,
            user_metadata={"platform_invite_id": str(invite_id), "platform_role": "admin"},
        )
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["pending_invite"] is not None
        assert body["pending_invite"]["kind"] == "platform"
        assert body["pending_invite"]["role"] == "admin"
        assert body["pending_invite"]["id"] == str(invite_id)
    finally:
        for stmt in (
            "DELETE FROM platform_invites WHERE id = :iid",
            "DELETE FROM auth.users WHERE id = :id",
        ):
            await db_session.execute(text(stmt), {"id": str(user_id), "iid": str(invite_id)})
        await db_session.commit()
