"""Tests for POST/GET/DELETE /api/tenants/{tid}/invites."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _insert_auth_user(db: AsyncSession, user_id, email: str) -> None:
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )


async def _seed_owner(db: AsyncSession) -> tuple:
    user_id = uuid4()
    email = f"o-{user_id.hex[:8]}@example.com"
    await _insert_auth_user(db, user_id, email)
    slug = f"t-{user_id.hex[:8]}"
    await db.execute(
        text("INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"),
        {"slug": slug, "name": "T", "uid": str(user_id)},
    )
    tid = (
        await db.execute(text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": slug})
    ).scalar_one()
    await db.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (:tid, :uid, 'owner')"
        ),
        {"tid": str(tid), "uid": str(user_id)},
    )
    await db.commit()
    return user_id, tid


async def _cleanup(db: AsyncSession, user_id) -> None:
    for stmt in (
        "DELETE FROM tenant_invites WHERE invited_by = :id",
        "DELETE FROM tenant_memberships WHERE user_id = :id",
        "DELETE FROM tenants WHERE created_by = :id",
        "DELETE FROM auth.users WHERE id = :id",
    ):
        await db.execute(text(stmt), {"id": str(user_id)})
    await db.commit()


async def test_owner_invites_admin(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt,
    mock_supabase_admin: MagicMock,
) -> None:
    user_id, tid = await _seed_owner(db_session)
    try:
        mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "alice@example.com", "role": "admin"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["role"] == "admin"
        assert body["tenant_id"] == str(tid)
        assert mock_supabase_admin.auth.admin.invite_user_by_email.called
        args, kwargs = mock_supabase_admin.auth.admin.invite_user_by_email.call_args
        assert args[0] == "alice@example.com"
        assert kwargs["data"]["tenant_invite_id"] == body["id"]
        assert kwargs["data"]["tenant_id"] == str(tid)
        assert kwargs["data"]["tenant_role"] == "admin"
    finally:
        await _cleanup(db_session, user_id)


async def test_admin_cannot_invite_admin(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    owner_id, tid = await _seed_owner(db_session)
    admin_id = uuid4()
    email = f"adm-{admin_id.hex[:8]}@example.com"
    await _insert_auth_user(db_session, admin_id, email)
    await db_session.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (:tid, :uid, 'admin')"
        ),
        {"tid": str(tid), "uid": str(admin_id)},
    )
    await db_session.commit()
    try:
        token = make_jwt(sub=admin_id)
        r = await http_client.post(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@x.com", "role": "admin"},
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "forbidden_role"
    finally:
        for stmt in (
            "DELETE FROM tenant_memberships WHERE user_id = :id",
            "DELETE FROM auth.users WHERE id = :id",
        ):
            await db_session.execute(text(stmt), {"id": str(admin_id)})
        await db_session.commit()
        await _cleanup(db_session, owner_id)


async def test_non_member_cannot_invite(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    owner_id, tid = await _seed_owner(db_session)
    outsider_id = uuid4()
    await _insert_auth_user(db_session, outsider_id, f"out-{outsider_id.hex[:8]}@example.com")
    await db_session.commit()
    try:
        token = make_jwt(sub=outsider_id)
        r = await http_client.post(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@x.com", "role": "editor"},
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "not_a_member"
    finally:
        await db_session.execute(
            text("DELETE FROM auth.users WHERE id = :id"), {"id": str(outsider_id)}
        )
        await db_session.commit()
        await _cleanup(db_session, owner_id)


async def test_owner_role_rejected_by_rule(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    user_id, tid = await _seed_owner(db_session)
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@x.com", "role": "owner"},
        )
        # 'owner' is a valid TenantRole enum value (pydantic accepts it);
        # can_invite() rejects target=owner -> ForbiddenRoleError -> 403.
        assert r.status_code == 403
        assert r.json()["detail"] == "forbidden_role"
    finally:
        await _cleanup(db_session, user_id)


async def test_list_and_revoke(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt,
    mock_supabase_admin: MagicMock,
) -> None:
    user_id, tid = await _seed_owner(db_session)
    try:
        mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
        token = make_jwt(sub=user_id)
        c = await http_client.post(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "listed@example.com", "role": "editor"},
        )
        assert c.status_code == 201
        invite_id = c.json()["id"]
        lst = await http_client.get(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert lst.status_code == 200
        assert any(i["email"] == "listed@example.com" for i in lst.json()["items"])
        d = await http_client.delete(
            f"/api/tenants/{tid}/invites/{invite_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert d.status_code == 204
        row = (
            await db_session.execute(
                text("SELECT revoked_at FROM tenant_invites WHERE id = :id"),
                {"id": invite_id},
            )
        ).scalar_one()
        assert row is not None
    finally:
        await _cleanup(db_session, user_id)


async def test_non_member_cannot_list(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    owner_id, tid = await _seed_owner(db_session)
    outsider_id = uuid4()
    await _insert_auth_user(db_session, outsider_id, f"nl-{outsider_id.hex[:8]}@example.com")
    await db_session.commit()
    try:
        token = make_jwt(sub=outsider_id)
        r = await http_client.get(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "not_a_member"
    finally:
        await db_session.execute(
            text("DELETE FROM auth.users WHERE id = :id"), {"id": str(outsider_id)}
        )
        await db_session.commit()
        await _cleanup(db_session, owner_id)
