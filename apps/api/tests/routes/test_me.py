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
    http_client: AsyncClient, existing_super_admin: PlatformUser, make_jwt
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == existing_super_admin.email
    assert body["platform"]["role"] == existing_super_admin.role.value
    assert body["tenants"] == []
    assert body["pending_invite"] is None
    # P3b additive: resolver-derived effective platform permissions. super_admin
    # holds the full platform set (incl. the super_admin-only roles.manage).
    perms = body["platform_permissions"]
    assert isinstance(perms, list)
    assert "platform.roles.manage" in perms
    assert "platform.users.invite" in perms
    assert "platform.settings.manage" in perms
    assert perms == sorted(perms)


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
    tid = (
        await db_session.execute(
            text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": slug}
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
            "VALUES (:tid, :uid, 'owner')"
        ),
        {"tid": str(tid), "uid": str(user_id)},
    )
    # Seed the workspace system roles + owner grant so /me returns the
    # resolver-derived effective workspace permissions (the P3b authz source).
    from xtrusio_api.rbac.grants import grant_role
    from xtrusio_api.rbac.reconcile import wire_workspace_role_perms

    await db_session.execute(
        text(
            "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
            "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
            "('owner'),('admin'),('editor'),('read_only')) AS v(key) "
            "ON CONFLICT DO NOTHING"
        ),
        {"t": str(tid)},
    )
    await wire_workspace_role_perms(db_session, workspace_id=tid)
    await grant_role(
        db_session, auth_user_id=user_id, scope="workspace", key="owner", workspace_id=tid
    )
    await db_session.commit()
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["platform"] is None
        assert body["platform_permissions"] == []
        assert len(body["tenants"]) == 1
        assert body["tenants"][0]["role"] == "owner"
        assert body["tenants"][0]["slug"] == slug
        # P3b additive: owner holds the full workspace permission set.
        tperms = body["tenants"][0]["permissions"]
        assert "workspace.roles.manage" in tperms
        assert "workspace.members.invite" in tperms
        assert "workspace.members.manage" in tperms
        assert tperms == sorted(tperms)
        assert body["pending_invite"] is None
    finally:
        await db_session.execute(
            text("DELETE FROM user_roles WHERE auth_user_id = :id"),
            {"id": str(user_id)},
        )
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
        assert body["platform_permissions"] == []
        assert body["tenants"] == []
        assert body["pending_invite"] is None
    finally:
        await db_session.execute(
            text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)}
        )
        await db_session.commit()


async def test_me_with_pending_platform_invite(
    http_client: AsyncClient, existing_super_admin, make_jwt, db_session: AsyncSession
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
            "inv": str(existing_super_admin.id),
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
