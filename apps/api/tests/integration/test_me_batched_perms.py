"""Batched workspace-perms query for /me (PAR-D H6).

Asserts ``effective_workspace_perms_batch`` returns, per workspace, exactly what
the per-workspace ``effective_workspace_perms`` returns — so collapsing the
N-query loop into one aggregation changed performance, not results.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.core.permissions import (
    effective_workspace_perms,
    effective_workspace_perms_batch,
)
from xtrusio_api.rbac.reconcile import wire_workspace_role_perms

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_owner_in_new_workspace() -> tuple[UUID, UUID]:
    uid, tid = uuid4(), uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": f"meb-{uid.hex[:8]}@example.com"},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:sl,:n,:c)"),
            {"t": str(tid), "sl": f"meb-{tid.hex[:8]}", "n": "Me-batch probe", "c": str(uid)},
        )
        await s.execute(
            text(
                "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
                "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
                "('owner'),('admin'),('editor'),('read_only')) AS v(key)"
            ),
            {"t": str(tid)},
        )
        await wire_workspace_role_perms(s, workspace_id=tid)
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation','on', true)"))
        await s.execute(
            text(
                "INSERT INTO user_roles (auth_user_id, role_id, workspace_id) "
                "SELECT :u, r.id, :t FROM roles r "
                "WHERE r.scope='workspace' AND r.workspace_id=:t AND r.key='owner'"
            ),
            {"u": str(uid), "t": str(tid)},
        )
        await s.commit()
    return uid, tid


async def _teardown(tid: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation','on', true)"))
        await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tid)})
        await s.commit()


async def test_batch_matches_per_workspace() -> None:
    uid, tid = await _make_owner_in_new_workspace()
    try:
        async with SessionLocal() as s:
            single = await effective_workspace_perms(s, uid, tid)
            batch = await effective_workspace_perms_batch(s, uid, [tid])
        assert single, "owner should hold workspace perms (setup sanity)"
        assert batch.get(tid) == single
    finally:
        await _teardown(tid)


async def test_batch_empty_input_returns_empty() -> None:
    async with SessionLocal() as s:
        assert await effective_workspace_perms_batch(s, uuid4(), []) == {}


async def test_batch_unknown_workspace_absent_from_map() -> None:
    async with SessionLocal() as s:
        assert await effective_workspace_perms_batch(s, uuid4(), [uuid4()]) == {}
