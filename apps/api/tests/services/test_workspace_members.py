"""Service-layer tests for ``list_workspace_members``."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.core.pagination import decode_cursor
from xtrusio_api.services.workspace_members import list_workspace_members

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_user_and_tenant(label: str) -> tuple[UUID, UUID]:
    """Seed @example.com auth.user + a tenant they own. Returns (uid, tid).

    Also runs reconcile so the workspace's per-tenant system roles exist —
    the helper ``_seed_grant_in_workspace`` looks them up by name.
    """
    uid, tid = uuid4(), uuid4()
    email = f"{label}-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"{label}-{tid.hex[:8]}", "n": "wm test", "u": str(uid)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await s.commit()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return uid, tid


async def _add_member(tid: UUID, label: str, role: str = "editor") -> UUID:
    uid = uuid4()
    email = f"{label}-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) " "VALUES (:t, :u, :r)"
            ),
            {"t": str(tid), "u": str(uid), "r": role},
        )
        await s.commit()
    return uid


async def _seed_grant_in_workspace(uid: UUID, tid: UUID, role_key: str = "editor") -> UUID:
    """Seed a workspace-scope user_roles grant. Returns the grant id for cleanup."""
    grant_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        role_id = (
            await s.execute(
                text(
                    "SELECT id FROM roles WHERE scope='workspace' "
                    "AND workspace_id = :w AND key = :k AND is_system"
                ),
                {"w": str(tid), "k": role_key},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO user_roles (id, auth_user_id, role_id, workspace_id, granted_by) "
                "VALUES (:id, :u, :r, :w, NULL)"
            ),
            {"id": str(grant_id), "u": str(uid), "r": str(role_id), "w": str(tid)},
        )
        await s.commit()
    return grant_id


async def _delete_tenant(tid: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tid)})
        await s.commit()


async def _delete_user(uid: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(text("DELETE FROM user_roles WHERE auth_user_id = :u"), {"u": str(uid)})
        await s.execute(
            text("DELETE FROM tenant_memberships WHERE user_id = :u"),
            {"u": str(uid)},
        )
        await s.execute(text("DELETE FROM platform_users WHERE id = :u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(uid)})
        await s.commit()


async def test_list_returns_only_workspace_members(db_session: AsyncSession) -> None:
    owner, tid = await _seed_user_and_tenant("p6da-wm-only")
    m1 = await _add_member(tid, "p6da-wm-only-m1")
    m2 = await _add_member(tid, "p6da-wm-only-m2")
    try:
        rows, _ = await list_workspace_members(db_session, workspace_id=tid, limit=200)
        ids = {UUID(str(r["user_id"])) for r in rows}
        assert ids == {owner, m1, m2}
    finally:
        await _delete_user(m1)
        await _delete_user(m2)
        await _delete_tenant(tid)
        await _delete_user(owner)


async def test_list_isolates_workspaces(db_session: AsyncSession) -> None:
    """A member of workspace B must not appear in workspace A's list."""
    owner_a, tid_a = await _seed_user_and_tenant("p6da-wm-iso-a")
    owner_b, tid_b = await _seed_user_and_tenant("p6da-wm-iso-b")
    m_b = await _add_member(tid_b, "p6da-wm-iso-b-m")
    try:
        rows, _ = await list_workspace_members(db_session, workspace_id=tid_a, limit=200)
        ids = {UUID(str(r["user_id"])) for r in rows}
        assert owner_a in ids
        assert m_b not in ids
        assert owner_b not in ids
    finally:
        await _delete_user(m_b)
        await _delete_tenant(tid_a)
        await _delete_tenant(tid_b)
        await _delete_user(owner_a)
        await _delete_user(owner_b)


async def test_list_paginates_via_cursor(db_session: AsyncSession) -> None:
    """Walking with limit=1 returns each member without repeats."""
    owner, tid = await _seed_user_and_tenant("p6da-wm-page")
    m1 = await _add_member(tid, "p6da-wm-page-m1")
    m2 = await _add_member(tid, "p6da-wm-page-m2")
    try:
        seen: set[UUID] = set()
        cursor: tuple[object, object] | None = None
        safety = 0
        while safety < 100:
            rows, next_cursor = await list_workspace_members(
                db_session,
                workspace_id=tid,
                cursor=cursor,  # type: ignore[arg-type]
                limit=1,
            )
            for r in rows:
                seen.add(UUID(str(r["user_id"])))
            if next_cursor is None:
                break
            cursor = decode_cursor(next_cursor)
            safety += 1
        assert seen == {owner, m1, m2}
    finally:
        await _delete_user(m1)
        await _delete_user(m2)
        await _delete_tenant(tid)
        await _delete_user(owner)


async def test_list_returns_member_email_from_left_join(db_session: AsyncSession) -> None:
    """LEFT JOIN to auth.users surfaces each member's email.

    ``tenant_memberships.user_id`` FKs to ``auth.users(id)`` with ON DELETE
    CASCADE in production, so a membership pointing at a missing auth row is
    not a state the service can ever observe. The LEFT JOIN exists as a
    schema-level guard so a future FK loosening (or a test that bypasses
    cascading) cannot break the listing — the service returns the row with
    ``email=None`` rather than dropping it. This test exercises the working
    case; the null branch is verified at the schema layer (``EmailStr | None``).
    """
    owner, tid = await _seed_user_and_tenant("p6da-wm-email")
    member = await _add_member(tid, "p6da-wm-email-m")
    try:
        rows, _ = await list_workspace_members(db_session, workspace_id=tid, limit=200)
        by_uid = {UUID(str(r["user_id"])): r for r in rows}
        assert by_uid[member]["email"] is not None
        assert "p6da-wm-email-m-" in str(by_uid[member]["email"])
    finally:
        await _delete_user(member)
        await _delete_tenant(tid)
        await _delete_user(owner)


async def test_list_includes_grant_count_per_member(db_session: AsyncSession) -> None:
    """granted_role_count counts only workspace-scope grants for THIS workspace.

    Owner has 1 grant (auto-wired by reconcile from their `owner` membership).
    Member has 1 explicit grant we seed via ``_seed_grant_in_workspace``; the
    member was added AFTER reconcile so they aren't auto-wired.
    """
    owner, tid = await _seed_user_and_tenant("p6da-wm-cnt")
    member = await _add_member(tid, "p6da-wm-cnt-m")
    grant_id = await _seed_grant_in_workspace(member, tid, role_key="editor")
    try:
        rows, _ = await list_workspace_members(db_session, workspace_id=tid, limit=200)
        by_uid = {UUID(str(r["user_id"])): r for r in rows}
        assert by_uid[member]["granted_role_count"] == 1
        assert by_uid[owner]["granted_role_count"] == 1
    finally:
        async with SessionLocal() as s:
            await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
            await s.execute(text("DELETE FROM user_roles WHERE id = :id"), {"id": str(grant_id)})
            await s.commit()
        await _delete_user(member)
        await _delete_tenant(tid)
        await _delete_user(owner)
