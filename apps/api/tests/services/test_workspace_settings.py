"""Service-layer tests for workspace settings get/update.

Audit-log assertions cover the rule: write a row ONLY when ``name`` actually
changed. No-op updates are silent (no audit noise).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.workspace_settings import (
    WorkspaceNotFoundError,
    get_workspace_settings,
    update_workspace_settings,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_actor_and_tenant(label: str) -> tuple[UUID, UUID]:
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
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"{label}-{tid.hex[:8]}", "n": "before", "u": str(uid)},
        )
        await s.commit()
    return uid, tid


async def _cleanup_tenant(tid: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE workspace_id = :w"),
            {"w": str(tid)},
        )
        await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tid)})
        await s.commit()


async def _cleanup_user(uid: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(uid)})
        await s.commit()


async def _audit_count_for_workspace(workspace_id: UUID, action: str) -> int:
    async with SessionLocal() as s:
        return int(
            (
                await s.execute(
                    text(
                        "SELECT count(*) FROM rbac_audit_log "
                        "WHERE workspace_id = :w AND action = :a"
                    ),
                    {"w": str(workspace_id), "a": action},
                )
            ).scalar_one()
        )


async def test_get_returns_settings(db_session: AsyncSession) -> None:
    actor, tid = await _seed_actor_and_tenant("p6da-ws-get")
    try:
        row = await get_workspace_settings(db_session, workspace_id=tid)
        assert UUID(str(row["id"])) == tid
        assert row["name"] == "before"
        assert row["slug"].startswith("p6da-ws-get-")
        assert row["created_at"] is not None
        assert row["updated_at"] is not None
    finally:
        await _cleanup_tenant(tid)
        await _cleanup_user(actor)


async def test_get_raises_when_workspace_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(WorkspaceNotFoundError):
        await get_workspace_settings(db_session, workspace_id=uuid4())


async def test_update_changes_name_and_writes_audit(db_session: AsyncSession) -> None:
    actor, tid = await _seed_actor_and_tenant("p6da-ws-upd")
    try:
        out = await update_workspace_settings(
            db_session, actor_id=actor, workspace_id=tid, name="after"
        )
        await db_session.commit()
        assert out["name"] == "after"
        # Subsequent GET returns the new value.
        re_read = await get_workspace_settings(db_session, workspace_id=tid)
        assert re_read["name"] == "after"
        # Audit row written with action workspace.settings.updated.
        assert (await _audit_count_for_workspace(tid, "workspace.settings.updated")) == 1
    finally:
        await _cleanup_tenant(tid)
        await _cleanup_user(actor)


async def test_update_noop_does_not_write_audit(db_session: AsyncSession) -> None:
    actor, tid = await _seed_actor_and_tenant("p6da-ws-noop")
    try:
        out = await update_workspace_settings(
            db_session, actor_id=actor, workspace_id=tid, name="before"
        )
        await db_session.commit()
        assert out["name"] == "before"
        assert (await _audit_count_for_workspace(tid, "workspace.settings.updated")) == 0
    finally:
        await _cleanup_tenant(tid)
        await _cleanup_user(actor)


async def test_update_raises_when_workspace_not_found(db_session: AsyncSession) -> None:
    actor = uuid4()
    with pytest.raises(WorkspaceNotFoundError):
        await update_workspace_settings(
            db_session, actor_id=actor, workspace_id=uuid4(), name="anything"
        )


async def test_update_audit_payload_has_before_and_after(db_session: AsyncSession) -> None:
    """Audit row carries before/after JSON with the old + new name."""
    actor, tid = await _seed_actor_and_tenant("p6da-ws-aud")
    try:
        await update_workspace_settings(
            db_session, actor_id=actor, workspace_id=tid, name="rebrand"
        )
        await db_session.commit()
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT before, after FROM rbac_audit_log "
                        "WHERE workspace_id = :w AND action = 'workspace.settings.updated'"
                    ),
                    {"w": str(tid)},
                )
            ).one()
            before, after = row
            assert before == {"name": "before"}
            assert after == {"name": "rebrand"}
    finally:
        await _cleanup_tenant(tid)
        await _cleanup_user(actor)
