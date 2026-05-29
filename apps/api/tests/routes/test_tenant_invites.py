"""Tests for POST/GET/DELETE /api/tenants/{tid}/invites."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _insert_auth_user(db: AsyncSession, user_id: UUID, email: str) -> None:
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )


async def _seed_workspace_roles(db: AsyncSession, tid: UUID) -> None:
    """Seed the 4 workspace system roles for `tid` and wire their
    role_permissions to the catalog (the P3b authz precondition that the
    startup reconciler provides for real tenants; tests create tenants
    mid-run, so we do it explicitly — same shape as P3a grant tests)."""
    from xtrusio_api.rbac.reconcile import wire_workspace_role_perms

    await db.execute(
        text(
            "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
            "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
            "('owner'),('admin'),('editor'),('read_only')) AS v(key) "
            "ON CONFLICT DO NOTHING"
        ),
        {"t": str(tid)},
    )
    await wire_workspace_role_perms(db, workspace_id=tid)


async def _seed_member_with_grant(
    db: AsyncSession, *, tid: UUID, user_id: UUID, enum_role: str, grant_key: str | None
) -> None:
    """Insert a tenant_memberships row (the enum, kept for can_invite) and,
    when `grant_key` is given, a resolver-visible workspace `user_roles` grant
    (the P3b authz source)."""
    from xtrusio_api.rbac.grants import grant_role

    await db.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) " "VALUES (:tid, :uid, :r)"
        ),
        {"tid": str(tid), "uid": str(user_id), "r": enum_role},
    )
    if grant_key is not None:
        await grant_role(
            db, auth_user_id=user_id, scope="workspace", key=grant_key, workspace_id=tid
        )


async def _seed_owner(db: AsyncSession) -> tuple[UUID, UUID]:
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
    await _seed_workspace_roles(db, tid)
    await _seed_member_with_grant(
        db, tid=tid, user_id=user_id, enum_role="owner", grant_key="owner"
    )
    await db.commit()
    return user_id, tid


async def _cleanup(db: AsyncSession, user_id: UUID) -> None:
    # FK-safe order: invites & grants & memberships first, then the tenant
    # (its workspace roles cascade via roles.workspace_id ON DELETE CASCADE),
    # then the auth user. user_roles for the tenant's workspace roles are
    # removed by the roles cascade; the owner's grant is dropped explicitly.
    for stmt in (
        "DELETE FROM tenant_invites WHERE invited_by = :id",
        "DELETE FROM user_roles WHERE auth_user_id = :id",
        "DELETE FROM tenant_memberships WHERE user_id = :id",
        "DELETE FROM tenants WHERE created_by = :id",
        "DELETE FROM auth.users WHERE id = :id",
    ):
        await db.execute(text(stmt), {"id": str(user_id)})
    await db.commit()


async def test_owner_invites_admin(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    user_id, tid = await _seed_owner(db_session)
    sb_uid = str(uuid4())
    try:
        mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock(
            user=MagicMock(id=sb_uid)
        )
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
        # PAR-D H5: create stages an outbox row instead of calling Supabase on
        # the request path. Assert the enqueued app_metadata + that Supabase was
        # untouched. (Tenant invites carry no writeback — no supabase_user_id.)
        mock_supabase_admin.auth.admin.invite_user_by_email.assert_not_called()
        payload = (
            await db_session.execute(
                text(
                    "SELECT payload FROM invite_email_outbox "
                    "WHERE payload->>'email' = :e ORDER BY created_at DESC LIMIT 1"
                ),
                {"e": "alice@example.com"},
            )
        ).scalar_one()
        assert payload["email"] == "alice@example.com"
        assert payload["app_metadata"]["tenant_invite_id"] == body["id"]
        assert payload["app_metadata"]["tenant_id"] == str(tid)
        assert payload["app_metadata"]["tenant_role"] == "admin"
        assert "writeback" not in payload
        await db_session.execute(
            text("DELETE FROM invite_email_outbox WHERE payload->>'email' = :e"),
            {"e": "alice@example.com"},
        )
        await db_session.commit()
    finally:
        await _cleanup(db_session, user_id)


async def test_admin_cannot_invite_admin(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt: Callable[..., str]
) -> None:
    # The admin HAS workspace.members.invite (P3b authz passes); the
    # can_invite() BUSINESS rule still rejects admin->admin (preserved).
    owner_id, tid = await _seed_owner(db_session)
    admin_id = uuid4()
    email = f"adm-{admin_id.hex[:8]}@example.com"
    await _insert_auth_user(db_session, admin_id, email)
    await _seed_member_with_grant(
        db_session, tid=tid, user_id=admin_id, enum_role="admin", grant_key="admin"
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
            "DELETE FROM user_roles WHERE auth_user_id = :id",
            "DELETE FROM tenant_memberships WHERE user_id = :id",
            "DELETE FROM auth.users WHERE id = :id",
        ):
            await db_session.execute(text(stmt), {"id": str(admin_id)})
        await db_session.commit()
        await _cleanup(db_session, owner_id)


async def test_non_member_cannot_invite(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt: Callable[..., str]
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
    http_client: AsyncClient, db_session: AsyncSession, make_jwt: Callable[..., str]
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
    make_jwt: Callable[..., str],
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
    http_client: AsyncClient, db_session: AsyncSession, make_jwt: Callable[..., str]
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


async def test_list_tenant_invites_paginates(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    from xtrusio_api.models.tenant_membership import TenantRole
    from xtrusio_api.services.tenant_invites import create_tenant_invite

    user_id, tid = await _seed_owner(db_session)
    try:
        mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
        for i in range(3):
            await create_tenant_invite(
                db_session,
                tenant_id=tid,
                inviter_id=user_id,
                email=f"paginv-{i}-{uuid4().hex[:6]}@example.com",
                role=TenantRole.ADMIN,
            )
        await db_session.commit()  # PAR-D M1: service is now caller-owns-tx

        token = make_jwt(sub=user_id)
        headers = {"Authorization": f"Bearer {token}"}

        r1 = await http_client.get(f"/api/tenants/{tid}/invites?limit=2", headers=headers)
        assert r1.status_code == 200, r1.text
        p1 = r1.json()
        assert len(p1["items"]) == 2
        assert p1["next_cursor"] is not None

        r2 = await http_client.get(
            f"/api/tenants/{tid}/invites?limit=2&cursor={p1['next_cursor']}",
            headers=headers,
        )
        assert r2.status_code == 200, r2.text
        p2 = r2.json()
        assert len(p2["items"]) >= 1
        assert {x["id"] for x in p1["items"]}.isdisjoint({x["id"] for x in p2["items"]})
    finally:
        await _cleanup(db_session, user_id)


async def test_list_tenant_invites_rejects_bad_cursor(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt: Callable[..., str]
) -> None:
    user_id, tid = await _seed_owner(db_session)
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.get(
            f"/api/tenants/{tid}/invites?cursor=NOPE",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
    finally:
        await _cleanup(db_session, user_id)


async def test_member_without_manage_perm_cannot_list_permission_denied(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt: Callable[..., str]
) -> None:
    # P3b authz model: a workspace member who is NOT owner/admin (editor enum +
    # editor grant -> no workspace.members.manage) IS a member (so NOT the
    # not_a_member contract) but is denied with the unified permission_denied.
    owner_id, tid = await _seed_owner(db_session)
    editor_id = uuid4()
    await _insert_auth_user(db_session, editor_id, f"ed-{editor_id.hex[:8]}@example.com")
    await _seed_member_with_grant(
        db_session, tid=tid, user_id=editor_id, enum_role="editor", grant_key="editor"
    )
    await db_session.commit()
    try:
        token = make_jwt(sub=editor_id)
        r = await http_client.get(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "permission_denied"
    finally:
        for stmt in (
            "DELETE FROM user_roles WHERE auth_user_id = :id",
            "DELETE FROM tenant_memberships WHERE user_id = :id",
            "DELETE FROM auth.users WHERE id = :id",
        ):
            await db_session.execute(text(stmt), {"id": str(editor_id)})
        await db_session.commit()
        await _cleanup(db_session, owner_id)
