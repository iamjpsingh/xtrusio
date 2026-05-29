"""Concurrent onboarding is serialised by an advisory lock (PAR-D M6).

Two parallel ``create_tenant_with_owner`` calls for the SAME user previously
both passed the membership existence-check and each created a tenant. The
``pg_advisory_xact_lock`` keyed on the user id makes check-then-create atomic.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.onboarding import AlreadyHasMembershipError, create_tenant_with_owner

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_user() -> UUID:
    uid = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": f"onb-race-{uid.hex[:8]}@example.com"},
        )
        await s.commit()
    return uid


async def _teardown(uid: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation','on', true)"))
        await s.execute(text("DELETE FROM tenants WHERE created_by = :u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(uid)})
        await s.commit()


async def test_concurrent_onboard_creates_exactly_one_tenant() -> None:
    uid = await _make_user()
    try:

        async def _onboard(name: str) -> str:
            async with SessionLocal() as s:
                try:
                    await create_tenant_with_owner(s, user_id=uid, workspace_name=name)
                    return "ok"
                except AlreadyHasMembershipError:
                    await s.rollback()
                    return "already"
                except DBAPIError:
                    # The lock-loser may instead hit statement_timeout waiting on
                    # the advisory lock if the winner's onboarding is slow — that
                    # still means the second tenant was prevented.
                    await s.rollback()
                    return "blocked"

        results = await asyncio.gather(_onboard("WS A"), _onboard("WS B"))
        assert [r for r in results if r == "ok"] == ["ok"], results  # exactly one winner
        async with SessionLocal() as s:
            n = (
                await s.execute(
                    text("SELECT count(*) FROM tenants WHERE created_by = :u"), {"u": str(uid)}
                )
            ).scalar_one()
        assert n == 1, f"expected exactly one tenant, got {n}"
    finally:
        await _teardown(uid)


async def test_sequential_second_onboard_rejected() -> None:
    """Deterministic companion: a second onboard for an already-member user is
    rejected (the existence check, now atomic under the lock)."""
    uid = await _make_user()
    try:
        async with SessionLocal() as s:
            await create_tenant_with_owner(s, user_id=uid, workspace_name="First WS")
        async with SessionLocal() as s:
            with pytest.raises(AlreadyHasMembershipError):
                await create_tenant_with_owner(s, user_id=uid, workspace_name="Second WS")
            await s.rollback()
    finally:
        await _teardown(uid)
