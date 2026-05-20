"""write_audit_event correctness."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.audit import write_audit_event

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_auth_user(db: AsyncSession, uid: UUID, label: str) -> None:
    """Insert a minimal @example.com auth.users row so FK actor_auth_user_id resolves.

    Matches the pattern used in tests/migrations/test_0009_triggers.py. The
    @example.com email convention ensures `_cleanup.purge_test_data` removes
    these rows (and their cascaded rbac_audit_log entries) on teardown.
    """
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) "
            "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
            "'authenticated', :email, '', now(), now(), now())"
        ),
        {"id": str(uid), "email": f"audit-{label}-{uid.hex[:8]}@example.com"},
    )


async def test_writes_one_row_with_all_fields(db_session: AsyncSession) -> None:
    actor = uuid4()
    target = uuid4()
    await _seed_auth_user(db_session, actor, "all")
    await db_session.commit()

    await write_audit_event(
        db_session,
        actor_id=actor,
        action="test_action",
        target_type="role",
        target_id=target,
        scope="platform",
        before={"name": "old"},
        after={"name": "new"},
    )
    await db_session.commit()
    row = (
        await db_session.execute(
            text(
                "SELECT actor_auth_user_id, action, target_type, target_id, scope, "
                "workspace_id, before, after FROM rbac_audit_log "
                "WHERE actor_auth_user_id = :a AND target_id = :t"
            ),
            {"a": str(actor), "t": str(target)},
        )
    ).one()
    assert row.action == "test_action"
    assert row.target_type == "role"
    assert row.before == {"name": "old"}
    assert row.after == {"name": "new"}
    assert row.scope == "platform"
    assert row.workspace_id is None


async def test_writes_null_payloads_when_omitted(db_session: AsyncSession) -> None:
    actor = uuid4()
    target = uuid4()
    await _seed_auth_user(db_session, actor, "null")
    await db_session.commit()

    await write_audit_event(
        db_session,
        actor_id=actor,
        action="x",
        target_type="role",
        target_id=target,
        scope="platform",
    )
    await db_session.commit()
    row = (
        await db_session.execute(
            text(
                "SELECT before, after FROM rbac_audit_log "
                "WHERE actor_auth_user_id = :a AND target_id = :t"
            ),
            {"a": str(actor), "t": str(target)},
        )
    ).one()
    assert row.before is None
    assert row.after is None


async def test_serializes_uuid_in_payload(db_session: AsyncSession) -> None:
    """UUIDs in before/after payloads must serialise (default=str)."""
    actor = uuid4()
    target = uuid4()
    nested_uuid = uuid4()
    await _seed_auth_user(db_session, actor, "uuid")
    await db_session.commit()

    await write_audit_event(
        db_session,
        actor_id=actor,
        action="x",
        target_type="role",
        target_id=target,
        scope="platform",
        after={"granted_to": nested_uuid},
    )
    await db_session.commit()
    row = (
        await db_session.execute(
            text("SELECT after FROM rbac_audit_log WHERE actor_auth_user_id = :a"),
            {"a": str(actor)},
        )
    ).one()
    # JSONB returns it as a Python string after json round-trip.
    assert row.after == {"granted_to": str(nested_uuid)}
