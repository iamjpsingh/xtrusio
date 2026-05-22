"""Service-layer tests for the workspace audit-log viewer."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.audit import write_audit_event
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.workspace_audit_log import list_workspace_audit_events

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_actor_and_workspace() -> tuple[UUID, UUID]:
    """Seed an @example.com auth.user + tenant. Returns (actor_id, workspace_id)."""
    uid, tid = uuid4(), uuid4()
    email = f"waudit-svc-{uid.hex[:8]}@example.com"
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
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"waudit-{tid.hex[:8]}", "n": "wa", "u": str(uid)},
        )
        await s.commit()
    return uid, tid


async def test_lists_workspace_scope_only(db_session: AsyncSession) -> None:
    actor, tid = await _seed_actor_and_workspace()
    await write_audit_event(
        db_session,
        actor_id=actor,
        action="test_p5d1_plat",
        target_type="role",
        target_id=uuid4(),
        scope="platform",
    )
    await write_audit_event(
        db_session,
        actor_id=actor,
        action="test_p5d1_ws",
        target_type="role",
        target_id=uuid4(),
        scope="workspace",
        workspace_id=tid,
    )
    await db_session.commit()
    rows, _ = await list_workspace_audit_events(db_session, workspace_id=tid, limit=200)
    mine = [r for r in rows if r["actor_auth_user_id"] == actor]
    assert len(mine) == 1
    assert mine[0]["action"] == "test_p5d1_ws"
    assert mine[0]["scope"] == "workspace"
    assert UUID(str(mine[0]["workspace_id"])) == tid


async def test_filters_to_this_workspace(db_session: AsyncSession) -> None:
    """An event in workspace B must not appear when listing workspace A."""
    actor_a, tid_a = await _seed_actor_and_workspace()
    actor_b, tid_b = await _seed_actor_and_workspace()
    await write_audit_event(
        db_session,
        actor_id=actor_a,
        action="test_p5d1_iso_a",
        target_type="role",
        target_id=uuid4(),
        scope="workspace",
        workspace_id=tid_a,
    )
    await write_audit_event(
        db_session,
        actor_id=actor_b,
        action="test_p5d1_iso_b",
        target_type="role",
        target_id=uuid4(),
        scope="workspace",
        workspace_id=tid_b,
    )
    await db_session.commit()
    rows, _ = await list_workspace_audit_events(db_session, workspace_id=tid_a, limit=200)
    actions = {r["action"] for r in rows if r["actor_auth_user_id"] in (actor_a, actor_b)}
    assert "test_p5d1_iso_a" in actions
    assert "test_p5d1_iso_b" not in actions


async def test_pagination_round_trip(db_session: AsyncSession) -> None:
    actor, tid = await _seed_actor_and_workspace()
    for i in range(3):
        await write_audit_event(
            db_session,
            actor_id=actor,
            action=f"test_p5d1_page.{i}",
            target_type="role",
            target_id=uuid4(),
            scope="workspace",
            workspace_id=tid,
        )
    await db_session.commit()
    from xtrusio_api.services.platform_audit_log import _decode_audit_cursor

    collected: list[dict[str, object]] = []
    cursor: tuple[object, int] | None = None
    safety = 0
    while safety < 50:
        rows, next_cursor = await list_workspace_audit_events(
            db_session,
            workspace_id=tid,
            cursor=cursor,  # type: ignore[arg-type]
            limit=2,
        )
        collected.extend(r for r in rows if r["actor_auth_user_id"] == actor)
        if next_cursor is None or len(collected) >= 3:
            break
        cursor = _decode_audit_cursor(next_cursor)
        safety += 1
    mine_actions = [
        str(r["action"]) for r in collected if str(r["action"]).startswith("test_p5d1_page.")
    ]
    assert set(mine_actions) == {
        "test_p5d1_page.0",
        "test_p5d1_page.1",
        "test_p5d1_page.2",
    }


async def test_workspace_actor_email_populated_when_actor_exists(
    db_session: AsyncSession,
) -> None:
    actor, tid = await _seed_actor_and_workspace()
    await write_audit_event(
        db_session,
        actor_id=actor,
        action="test_p6c_s2_ws_actor_email.create",
        target_type="role",
        target_id=uuid4(),
        scope="workspace",
        workspace_id=tid,
        after={"key": "viewer"},
    )
    await db_session.commit()
    rows, _ = await list_workspace_audit_events(db_session, workspace_id=tid, limit=200)
    assert rows, "seeded workspace audit row not returned"
    email = rows[0]["actor_email"]
    assert email is not None
    assert email.startswith("waudit-svc-")
    assert email.endswith("@example.com")


async def test_workspace_actor_email_none_when_actor_null(
    db_session: AsyncSession,
) -> None:
    _, tid = await _seed_actor_and_workspace()
    sentinel_target = uuid4()
    await db_session.execute(
        text(
            "INSERT INTO rbac_audit_log "
            "(actor_auth_user_id, action, target_type, target_id, scope, "
            "workspace_id, before, after, created_at) "
            "VALUES (NULL, 'test_p6c_s2_ws_system_event', 'role', :tid, "
            "'workspace', :wid, NULL, '{}'::jsonb, NOW())"
        ),
        {"tid": str(sentinel_target), "wid": str(tid)},
    )
    await db_session.commit()
    rows, _ = await list_workspace_audit_events(db_session, workspace_id=tid, limit=200)
    matching = [r for r in rows if r["target_id"] == str(sentinel_target)]
    assert matching, "system-emitted workspace audit row not returned"
    assert matching[0]["actor_email"] is None


async def test_workspace_actor_email_none_when_actor_hard_deleted(
    db_session: AsyncSession,
) -> None:
    # The tenant's `created_by` FK to auth.users is `ON DELETE RESTRICT`, so
    # we cannot delete the actor that owns the tenant. Seed a separate
    # `secondary_actor` that authored the audit event but does NOT own the
    # tenant — we can hard-delete that actor freely. The audit row's
    # `actor_auth_user_id` FK is `ON DELETE SET NULL`, so after deletion the
    # row keeps its identifying fields but loses the actor pointer.
    _, tid = await _seed_actor_and_workspace()
    secondary_actor = uuid4()
    sentinel_target = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {
                "id": str(secondary_actor),
                "e": f"waudit-svc-orphan-{secondary_actor.hex[:8]}@example.com",
            },
        )
        await s.commit()
    await write_audit_event(
        db_session,
        actor_id=secondary_actor,
        action="test_p6c_s2_ws_orphan.create",
        target_type="role",
        target_id=sentinel_target,
        scope="workspace",
        workspace_id=tid,
        after={"key": "ghost"},
    )
    await db_session.commit()
    await db_session.execute(
        text("DELETE FROM auth.users WHERE id = :id"),
        {"id": str(secondary_actor)},
    )
    await db_session.commit()
    rows, _ = await list_workspace_audit_events(db_session, workspace_id=tid, limit=200)
    orphaned = [r for r in rows if r["target_id"] == str(sentinel_target)]
    assert orphaned, "orphaned workspace audit row missing"
    assert orphaned[0]["actor_auth_user_id"] is None
    assert orphaned[0]["actor_email"] is None
