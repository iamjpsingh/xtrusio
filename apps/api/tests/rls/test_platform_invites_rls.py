"""platform_invites RLS — only super_admin sees."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

from tests.rls.conftest import RlsAs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_non_super_admin_cannot_see(rls_as: RlsAs, super_admin_user: PlatformUser) -> None:
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO platform_invites (email, role, invited_by, expires_at) "
                "VALUES (:e, 'admin', :inv, :exp)"
            ),
            {
                "e": "rlscheck@example.com",
                "inv": str(super_admin_user.id),
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        await priv.commit()
    user_id = uuid4()
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(user_id), "email": f"nope-{user_id.hex[:8]}@example.com"},
        )
        await priv.commit()
    try:
        async with rls_as(user_id) as s:
            rows = (await s.execute(text("SELECT email FROM platform_invites"))).all()
            assert rows == []
        async with rls_as(super_admin_user.id) as s:
            rows = (await s.execute(text("SELECT email FROM platform_invites"))).all()
            assert ("rlscheck@example.com",) in [tuple(r) for r in rows]
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text("DELETE FROM platform_invites WHERE email = :e"),
                {"e": "rlscheck@example.com"},
            )
            await priv.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await priv.commit()
