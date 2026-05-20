"""Service-layer tests for the platform audit-log viewer.

Seeds raw `rbac_audit_log` rows via `write_audit_event` to avoid coupling
these tests to the higher-level role/grant services. Each test creates one
or more @example.com auth.users actors so `_cleanup.purge_test_data` reliably
removes both the actors and their audit rows on teardown.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.audit import write_audit_event
from xtrusio_api.services.platform_audit_log import (
    _decode_audit_cursor,
    _encode_audit_cursor,
    list_platform_audit_events,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_actor(db: AsyncSession, uid: UUID, label: str) -> None:
    """Insert a minimal @example.com auth.users row so FK resolves and the
    session-scoped cleanup purges this actor + its audit rows on teardown.
    """
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) "
            "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
            "'authenticated', :email, '', now(), now(), now())"
        ),
        {"id": str(uid), "email": f"audit-svc-{label}-{uid.hex[:8]}@example.com"},
    )


async def test_lists_newest_first(db_session: AsyncSession) -> None:
    actor = uuid4()
    await _seed_actor(db_session, actor, "newest")
    await db_session.commit()
    targets = [uuid4(), uuid4(), uuid4()]
    for i, tgt in enumerate(targets):
        await write_audit_event(
            db_session,
            actor_id=actor,
            action=f"test_p4d1_newest.{i}",
            target_type="role",
            target_id=tgt,
            scope="platform",
        )
    await db_session.commit()

    rows, _ = await list_platform_audit_events(db_session, limit=200)
    mine = [r for r in rows if r["actor_auth_user_id"] == actor]
    assert len(mine) == 3
    # Strict newest-first ordering on created_at DESC, id DESC.
    assert all(mine[i]["created_at"] >= mine[i + 1]["created_at"] for i in range(len(mine) - 1))
    # Actions inserted in order 0,1,2; newest (=last inserted) is .2.
    actions = [r["action"] for r in mine]
    assert actions[0] == "test_p4d1_newest.2"
    assert actions[-1] == "test_p4d1_newest.0"


async def test_filters_to_platform_scope(db_session: AsyncSession) -> None:
    actor = uuid4()
    await _seed_actor(db_session, actor, "scope")
    # rbac_audit_log.workspace_id has a FK to tenants(id); seed a real tenant
    # so the workspace-scope row can be inserted. The tenant's created_by is
    # the @example.com actor we just inserted, so `purge_test_data` cleans it.
    ws_id = uuid4()
    await db_session.execute(
        text("INSERT INTO tenants (id, slug, name, created_by) " "VALUES (:t, :s, :n, :u)"),
        {
            "t": str(ws_id),
            "s": f"test-p4d1-scope-{ws_id.hex[:8]}",
            "n": "test p4d1 scope",
            "u": str(actor),
        },
    )
    await db_session.commit()
    plat_target = uuid4()
    ws_target = uuid4()
    await write_audit_event(
        db_session,
        actor_id=actor,
        action="test_p4d1_scope.platform",
        target_type="role",
        target_id=plat_target,
        scope="platform",
    )
    await write_audit_event(
        db_session,
        actor_id=actor,
        action="test_p4d1_scope.workspace",
        target_type="role",
        target_id=ws_target,
        scope="workspace",
        workspace_id=ws_id,
    )
    await db_session.commit()

    rows, _ = await list_platform_audit_events(db_session, limit=200)
    mine = [r for r in rows if r["actor_auth_user_id"] == actor]
    assert len(mine) == 1
    assert mine[0]["action"] == "test_p4d1_scope.platform"
    assert mine[0]["scope"] == "platform"


async def test_pagination_round_trip(db_session: AsyncSession) -> None:
    actor = uuid4()
    await _seed_actor(db_session, actor, "page")
    await db_session.commit()
    for i in range(3):
        await write_audit_event(
            db_session,
            actor_id=actor,
            action=f"test_p4d1_page.{i}",
            target_type="role",
            target_id=uuid4(),
            scope="platform",
        )
    await db_session.commit()

    # First page (limit=2 across THIS actor's rows). Other tests may have
    # written rows too, so we filter then assert on the union behaviour:
    # follow next_cursor until we've collected this actor's 3 rows.
    collected: list[dict[str, object]] = []
    cursor: tuple[datetime, int] | None = None
    safety = 0
    while safety < 50:
        rows, next_cursor = await list_platform_audit_events(db_session, cursor=cursor, limit=2)
        collected.extend(r for r in rows if r["actor_auth_user_id"] == actor)
        if next_cursor is None or len(collected) >= 3:
            break
        cursor = _decode_audit_cursor(next_cursor)
        safety += 1
    assert len(collected) >= 3
    mine_actions = [
        str(r["action"]) for r in collected if str(r["action"]).startswith("test_p4d1_page.")
    ]
    assert set(mine_actions) == {"test_p4d1_page.0", "test_p4d1_page.1", "test_p4d1_page.2"}


async def test_decode_invalid_cursor_raises() -> None:
    with pytest.raises(ValueError):
        _decode_audit_cursor("not-a-cursor")


async def test_encode_decode_round_trip() -> None:
    from datetime import UTC, datetime

    ts = datetime(2026, 1, 1, 12, 34, 56, tzinfo=UTC)
    token = _encode_audit_cursor(ts, 42)
    ts2, rid2 = _decode_audit_cursor(token)
    assert ts2 == ts
    assert rid2 == 42
