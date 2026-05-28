"""DB-level integrity guards added in migration 0010 (PAR-C slice 1).

Exercised directly via raw SQL against the shared managed DB. All test data
uses the ``@example.com`` convention and is swept by the session purge; each
test also tears down its own workspace under the bypass GUC.

Covers:
  - C5:  ``roles_super_admin_pinned_id`` CHECK exists and the seeded
         super_admin role satisfies it.
  - H10: ``trg_user_roles_owner_floor`` blocks revoking the last workspace
         owner, allows it when another owner remains, serialises concurrent
         revokes (exactly one wins), and is bypassed by the system GUC.
  - M17: ``set_updated_at()`` has a pinned ``search_path``.
  - 6.2.7: ``tenant_memberships`` per-action RLS policies replaced the FOR-ALL
         owner/admin policy.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")

_SUPER_ADMIN_ROLE_ID = "00000000-0000-0000-0000-0000000000a1"


async def _insert_auth_user(s: AsyncSession, *, email: str) -> UUID:
    uid = uuid4()
    await s.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) "
            "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
            "'authenticated', :email, '', now(), now(), now())"
        ),
        {"id": str(uid), "email": email},
    )
    return uid


async def _seed_workspace_with_owners(n: int) -> tuple[UUID, list[UUID]]:
    """Create a tenant + its workspace ``owner`` system role + ``n`` owner
    grants. Returns (tenant_id, [grant_ids]). Owner grants use granted_by=NULL
    so the 0009 priv-escalation INSERT trigger auto-bypasses."""
    tenant_id = uuid4()
    grant_ids: list[UUID] = []
    async with SessionLocal() as s:
        creator = await _insert_auth_user(s, email=f"of-creator-{tenant_id.hex[:8]}@example.com")
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:sl,:n,:c)"),
            {
                "t": str(tenant_id),
                "sl": f"of-{tenant_id.hex[:8]}",
                "n": "Owner-floor probe",
                "c": str(creator),
            },
        )
        owner_role_id = uuid4()
        await s.execute(
            text(
                "INSERT INTO roles (id, scope, workspace_id, key, name, description, is_system) "
                "VALUES (:rid, 'workspace', :t, 'owner', 'Owner', '', true)"
            ),
            {"rid": str(owner_role_id), "t": str(tenant_id)},
        )
        for i in range(n):
            member = await _insert_auth_user(
                s, email=f"of-owner-{tenant_id.hex[:8]}-{i}@example.com"
            )
            gid = uuid4()
            await s.execute(
                text(
                    "INSERT INTO user_roles (id, auth_user_id, role_id, workspace_id, granted_by) "
                    "VALUES (:g, :u, :r, :t, NULL)"
                ),
                {"g": str(gid), "u": str(member), "r": str(owner_role_id), "t": str(tenant_id)},
            )
            grant_ids.append(gid)
        await s.commit()
    return tenant_id, grant_ids


async def _teardown_workspace(tenant_id: UUID) -> None:
    async with SessionLocal() as s:
        # Bypass the owner-floor + governance triggers for teardown.
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
        await s.commit()


async def _set_actor(s: AsyncSession) -> None:
    """Tag the tx with an actor so the owner-floor trigger treats the DELETE as
    an actor-driven application revoke (the path the floor guards). The actor's
    identity is irrelevant — the trigger only checks that one is set."""
    await s.execute(text("SELECT set_config('app.actor_id', :a, true)"), {"a": str(uuid4())})


# --- C5 ---------------------------------------------------------------------


async def test_super_admin_pinned_check_exists_and_seed_satisfies_it() -> None:
    async with SessionLocal() as s:
        present = (
            await s.execute(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname = 'roles_super_admin_pinned_id'"
                )
            )
        ).scalar_one()
        assert present == 1, "C5 CHECK constraint roles_super_admin_pinned_id missing"
        # The live seed must satisfy the pin (id = …00a1).
        seed_id = (
            await s.execute(
                text(
                    "SELECT id FROM roles "
                    "WHERE scope='platform' AND key='super_admin' AND is_system"
                )
            )
        ).scalar_one()
        assert str(seed_id) == _SUPER_ADMIN_ROLE_ID


# --- H10 owner floor --------------------------------------------------------


async def test_owner_floor_blocks_revoking_only_owner() -> None:
    tenant_id, grants = await _seed_workspace_with_owners(1)
    try:
        async with SessionLocal() as s:
            await _set_actor(s)
            with pytest.raises(DBAPIError) as exc:
                await s.execute(text("DELETE FROM user_roles WHERE id = :g"), {"g": str(grants[0])})
            assert "last_owner" in str(exc.value)
            await s.rollback()
    finally:
        await _teardown_workspace(tenant_id)


async def test_owner_floor_allows_revoke_when_another_owner_remains() -> None:
    tenant_id, grants = await _seed_workspace_with_owners(2)
    try:
        async with SessionLocal() as s:
            await _set_actor(s)
            await s.execute(text("DELETE FROM user_roles WHERE id = :g"), {"g": str(grants[0])})
            await s.commit()
        # One owner remains; revoking it now must be blocked.
        async with SessionLocal() as s:
            await _set_actor(s)
            with pytest.raises(DBAPIError):
                await s.execute(text("DELETE FROM user_roles WHERE id = :g"), {"g": str(grants[1])})
            await s.rollback()
    finally:
        await _teardown_workspace(tenant_id)


async def test_owner_floor_concurrent_revoke_leaves_exactly_one() -> None:
    """Two sessions race to revoke the two (only) owner grants. The trigger's
    SELECT … FOR UPDATE on the workspace owner role serialises them: one
    commits, the other sees zero remaining owners and raises last_owner."""
    tenant_id, grants = await _seed_workspace_with_owners(2)
    try:

        async def _revoke(grant_id: UUID) -> str:
            async with SessionLocal() as s:
                try:
                    await _set_actor(s)
                    await s.execute(
                        text("DELETE FROM user_roles WHERE id = :g"), {"g": str(grant_id)}
                    )
                    await s.commit()
                    return "ok"
                except DBAPIError as e:
                    await s.rollback()
                    return "last_owner" if "last_owner" in str(e) else f"other:{e}"

        results = await asyncio.gather(_revoke(grants[0]), _revoke(grants[1]))
        assert sorted(results) == ["last_owner", "ok"], results
        # Exactly one owner grant survives.
        async with SessionLocal() as s:
            remaining = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                        "WHERE ur.workspace_id = :t AND r.key='owner' AND r.scope='workspace'"
                    ),
                    {"t": str(tenant_id)},
                )
            ).scalar_one()
            assert remaining == 1
    finally:
        await _teardown_workspace(tenant_id)


async def test_owner_floor_bypassed_by_system_guc() -> None:
    """System processes (purge, reconcile) set the bypass GUC and may delete
    even the last owner — otherwise test-data cleanup would deadlock on the
    floor."""
    tenant_id, grants = await _seed_workspace_with_owners(1)
    try:
        async with SessionLocal() as s:
            await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
            await s.execute(text("DELETE FROM user_roles WHERE id = :g"), {"g": str(grants[0])})
            await s.commit()
        async with SessionLocal() as s:
            gone = (
                await s.execute(
                    text("SELECT count(*) FROM user_roles WHERE id = :g"), {"g": str(grants[0])}
                )
            ).scalar_one()
            assert gone == 0
    finally:
        await _teardown_workspace(tenant_id)


# --- M17 --------------------------------------------------------------------


async def test_set_updated_at_has_pinned_search_path() -> None:
    async with SessionLocal() as s:
        proconfig = (
            await s.execute(text("SELECT proconfig FROM pg_proc WHERE proname = 'set_updated_at'"))
        ).scalar_one()
        assert proconfig is not None, "set_updated_at has no proconfig (search_path unpinned)"
        assert any(str(c).startswith("search_path=") for c in proconfig), proconfig


# --- 6.2.7 RLS split --------------------------------------------------------


async def test_tenant_memberships_rls_split() -> None:
    async with SessionLocal() as s:
        names = {
            r[0]
            for r in (
                await s.execute(
                    text(
                        "SELECT policyname FROM pg_policies WHERE tablename = 'tenant_memberships'"
                    )
                )
            ).all()
        }
    assert "tenant_memberships_owner_admin_manage" not in names, names
    for expected in (
        "tenant_memberships_member_select",
        "tenant_memberships_owner_admin_insert",
        "tenant_memberships_owner_admin_update",
        "tenant_memberships_owner_admin_delete",
    ):
        assert expected in names, (expected, names)
