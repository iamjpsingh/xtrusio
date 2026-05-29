"""Invite-email outbox worker (PAR-D H5).

Drives ``process_due_batch`` directly with a mocked Supabase client (the worker
loop itself is just a poll wrapper). Verifies: a due row is sent and marked
succeeded (with supabase_user_id written back for platform invites); a Supabase
failure increments attempts + backs off without marking the row succeeded.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services import invite_outbox

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, *, sb_uid: str | None, fail: bool) -> MagicMock:
    client = MagicMock()
    if fail:
        client.auth.admin.invite_user_by_email.side_effect = httpx.HTTPError("supabase down")
    else:
        client.auth.admin.invite_user_by_email.return_value = MagicMock(user=MagicMock(id=sb_uid))
    monkeypatch.setattr(invite_outbox, "create_client", lambda *a, **k: client)
    return client


async def _enqueue(
    email: str, app_metadata: dict[str, Any], writeback: dict[str, str] | None = None
) -> None:
    async with SessionLocal() as s:
        await invite_outbox.enqueue_invite_email(
            s, email=email, app_metadata=app_metadata, writeback=writeback
        )
        await s.commit()


async def _row(email: str) -> dict[str, Any]:
    async with SessionLocal() as s:
        return dict(
            (
                await s.execute(
                    text(
                        "SELECT attempts, succeeded_at, last_error FROM invite_email_outbox "
                        "WHERE payload->>'email' = :e ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"e": email},
                )
            )
            .mappings()
            .one()
        )


async def _cleanup(email: str) -> None:
    async with SessionLocal() as s:
        await s.execute(
            text("DELETE FROM invite_email_outbox WHERE payload->>'email' = :e"), {"e": email}
        )
        await s.commit()


async def test_send_marks_succeeded(monkeypatch: pytest.MonkeyPatch) -> None:
    email = f"obx-ok-{uuid4().hex[:8]}@example.com"
    _mock_supabase(monkeypatch, sb_uid=str(uuid4()), fail=False)
    await _enqueue(email, {"platform_invite_id": str(uuid4()), "platform_role": "admin"})
    try:
        sent = await invite_outbox.process_due_batch(SessionLocal)
        assert sent >= 1
        row = await _row(email)
        assert row["succeeded_at"] is not None
        assert row["last_error"] is None
    finally:
        await _cleanup(email)


async def test_failure_increments_attempts_and_backs_off(monkeypatch: pytest.MonkeyPatch) -> None:
    email = f"obx-fail-{uuid4().hex[:8]}@example.com"
    _mock_supabase(monkeypatch, sb_uid=None, fail=True)
    await _enqueue(email, {"platform_invite_id": str(uuid4()), "platform_role": "admin"})
    try:
        await invite_outbox.process_due_batch(SessionLocal)
        row = await _row(email)
        assert row["succeeded_at"] is None
        assert row["attempts"] == 1
        assert row["last_error"]
        # Backed off: not due again immediately, so a second poll is a no-op for it.
        async with SessionLocal() as s:
            due = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM invite_email_outbox "
                        "WHERE payload->>'email' = :e AND next_attempt_at <= now()"
                    ),
                    {"e": email},
                )
            ).scalar_one()
        assert due == 0
    finally:
        await _cleanup(email)


async def test_writeback_sets_platform_invite_supabase_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb_uid = str(uuid4())
    _mock_supabase(monkeypatch, sb_uid=sb_uid, fail=False)
    creator, invite_id = uuid4(), uuid4()
    email = f"obx-wb-{invite_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated','authenticated',"
                ":e,'',now(),now(),now())"
            ),
            {"id": str(creator), "e": f"obx-wb-creator-{creator.hex[:8]}@example.com"},
        )
        await s.execute(
            text(
                "INSERT INTO platform_invites (id, email, role, invited_by, expires_at) "
                "VALUES (:id, :e, 'admin', :by, :exp)"
            ),
            {
                "id": str(invite_id),
                "e": email,
                "by": str(creator),
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        await s.commit()
    await _enqueue(
        email,
        {"platform_invite_id": str(invite_id), "platform_role": "admin"},
        writeback={"table": "platform_invites", "id": str(invite_id)},
    )
    try:
        await invite_outbox.process_due_batch(SessionLocal)
        async with SessionLocal() as s:
            stored = (
                await s.execute(
                    text("SELECT supabase_user_id FROM platform_invites WHERE id = :id"),
                    {"id": str(invite_id)},
                )
            ).scalar_one()
        assert str(stored) == sb_uid
    finally:
        await _cleanup(email)
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM platform_invites WHERE id = :id"), {"id": str(invite_id)}
            )
            await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(creator)})
            await s.commit()
