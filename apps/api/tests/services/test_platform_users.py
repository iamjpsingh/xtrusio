"""Service-layer tests for ``list_platform_users``.

Test-data hygiene: every helper uses the @example.com convention so the
session-scoped purge in ``conftest`` sweeps anything a test forgets to clean.
The ``existing_super_admin`` operator row is exempt — tests filter by id when
asserting on counts so they never depend on other users' state.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.core.pagination import decode_cursor
from xtrusio_api.services.platform_users import list_platform_users

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_example_platform_user(label: str = "pu") -> UUID:
    """Seed @example.com auth.users + platform_users (no grants). Returns id."""
    uid = uuid4()
    email = f"{label}-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
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
        await s.commit()
    return uid


async def _cleanup_user(uid: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :u"),
            {"u": str(uid)},
        )
        await s.execute(
            text("DELETE FROM user_roles WHERE auth_user_id = :u OR granted_by = :u"),
            {"u": str(uid)},
        )
        await s.execute(text("DELETE FROM platform_users WHERE id = :u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(uid)})
        await s.commit()


async def _platform_role_id(key: str) -> UUID:
    async with SessionLocal() as s:
        rid = (
            await s.execute(
                text(
                    "SELECT id FROM roles WHERE scope='platform' "
                    "AND workspace_id IS NULL AND key=:k AND is_system"
                ),
                {"k": key},
            )
        ).scalar_one()
        return UUID(str(rid))


async def _seed_grant(user_id: UUID, role_id: UUID) -> UUID:
    """Insert a user_roles row directly (granted_by=NULL bypasses the trigger).
    Returns the grant id for cleanup.
    """
    grant_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO user_roles (id, auth_user_id, role_id, workspace_id, granted_by) "
                "VALUES (:id, :u, :r, NULL, NULL)"
            ),
            {"id": str(grant_id), "u": str(user_id), "r": str(role_id)},
        )
        await s.commit()
    return grant_id


async def _cleanup_grant(grant_id: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("DELETE FROM user_roles WHERE id = :id"), {"id": str(grant_id)})
        await s.commit()


async def test_list_returns_rows_for_seeded_users(db_session: AsyncSession) -> None:
    """Two seeded users must both appear in the listing (filtered by id)."""
    u1 = await _create_example_platform_user("p6da-pu-rows-a")
    u2 = await _create_example_platform_user("p6da-pu-rows-b")
    try:
        rows, _ = await list_platform_users(db_session, limit=200)
        ids = {UUID(str(r["id"])) for r in rows}
        assert u1 in ids
        assert u2 in ids
    finally:
        await _cleanup_user(u1)
        await _cleanup_user(u2)


async def test_list_orders_by_created_at_desc(db_session: AsyncSession) -> None:
    """Newer users come first when ordered DESC."""
    u1 = await _create_example_platform_user("p6da-pu-ord-a")
    # Force a created_at gap so the ordering is unambiguous.
    async with SessionLocal() as s:
        await s.execute(
            text("UPDATE platform_users SET created_at = now() - interval '1 hour' WHERE id = :id"),
            {"id": str(u1)},
        )
        await s.commit()
    u2 = await _create_example_platform_user("p6da-pu-ord-b")
    try:
        rows, _ = await list_platform_users(db_session, limit=200)
        ids = [UUID(str(r["id"])) for r in rows]
        idx_u1 = ids.index(u1) if u1 in ids else -1
        idx_u2 = ids.index(u2) if u2 in ids else -1
        assert idx_u1 != -1 and idx_u2 != -1
        assert idx_u2 < idx_u1, "newer user must appear before older user"
    finally:
        await _cleanup_user(u1)
        await _cleanup_user(u2)


async def test_list_paginates_via_cursor(db_session: AsyncSession) -> None:
    """Walking with limit=1 returns each seeded user across pages without repeats."""
    u1 = await _create_example_platform_user("p6da-pu-page-a")
    u2 = await _create_example_platform_user("p6da-pu-page-b")
    u3 = await _create_example_platform_user("p6da-pu-page-c")
    try:
        seen: set[UUID] = set()
        cursor: tuple[object, object] | None = None
        safety = 0
        while safety < 200:
            rows, next_cursor = await list_platform_users(
                db_session,
                cursor=cursor,  # type: ignore[arg-type]
                limit=1,
            )
            for r in rows:
                uid = UUID(str(r["id"]))
                if uid in {u1, u2, u3}:
                    seen.add(uid)
            if next_cursor is None or seen == {u1, u2, u3}:
                break
            cursor = decode_cursor(next_cursor)
            safety += 1
        assert seen == {u1, u2, u3}
    finally:
        await _cleanup_user(u1)
        await _cleanup_user(u2)
        await _cleanup_user(u3)


async def test_list_includes_granted_role_count(db_session: AsyncSession) -> None:
    """Seeded user with 1 platform grant must show granted_role_count == 1.

    A separate user with zero grants must show 0 — distinguishing zero from
    null/None (the LEFT JOIN/GROUP BY combination must aggregate to 0).
    """
    user_with_grant = await _create_example_platform_user("p6da-pu-cnt-a")
    user_no_grant = await _create_example_platform_user("p6da-pu-cnt-b")
    admin_role_id = await _platform_role_id("admin")
    grant_id = await _seed_grant(user_with_grant, admin_role_id)
    try:
        rows, _ = await list_platform_users(db_session, limit=200)
        by_id = {UUID(str(r["id"])): r for r in rows}
        assert by_id[user_with_grant]["granted_role_count"] == 1
        assert by_id[user_no_grant]["granted_role_count"] == 0
    finally:
        await _cleanup_grant(grant_id)
        await _cleanup_user(user_with_grant)
        await _cleanup_user(user_no_grant)


async def test_list_excludes_workspace_grants_from_platform_count(
    db_session: AsyncSession,
) -> None:
    """A workspace-scope grant must NOT count toward the user's
    ``granted_role_count`` — the count is platform-grants-only."""
    uid = await _create_example_platform_user("p6da-pu-ws-iso")
    tid = uuid4()
    # Seed a tenant; reconcile to wire its per-workspace system roles + grant
    # the creator the workspace owner role. After reconcile the user has
    # exactly ONE workspace-scope user_roles row (workspace_id NOT NULL) and
    # zero platform-scope grants — the LEFT JOIN must surface 0.
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {
                "t": str(tid),
                "s": f"p6da-pu-ws-{tid.hex[:8]}",
                "n": "scope-iso",
                "u": str(uid),
            },
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
    try:
        rows, _ = await list_platform_users(db_session, limit=200)
        by_id = {UUID(str(r["id"])): r for r in rows}
        # The workspace grant lives in user_roles but its workspace_id is NOT
        # NULL, so the LEFT JOIN's `workspace_id IS NULL` filter must drop it.
        assert by_id[uid]["granted_role_count"] == 0
    finally:
        async with SessionLocal() as s:
            await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
            await s.execute(
                text("DELETE FROM user_roles WHERE workspace_id = :w"),
                {"w": str(tid)},
            )
            await s.execute(
                text("DELETE FROM tenant_memberships WHERE tenant_id = :t"),
                {"t": str(tid)},
            )
            await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tid)})
            await s.commit()
        await _cleanup_user(uid)


async def test_list_empty_when_no_match(db_session: AsyncSession) -> None:
    """Encoded cursor far in the future returns no rows older than that.

    The platform_users table is never empty in the managed DB (the operator
    bootstrapped a super_admin), so we instead test that a cursor referencing
    a non-existent row id with a tiny created_at returns zero rows: the
    DESC ordering coupled with `created_at < :ts` will surface only earlier
    rows, of which there are none below the unix epoch.
    """
    from datetime import UTC, datetime

    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    cursor = (epoch, uuid4())
    rows, next_cursor = await list_platform_users(db_session, cursor=cursor, limit=200)
    assert rows == []
    assert next_cursor is None
