"""platform_settings RLS — non-super_admin cannot UPDATE; everyone can SELECT."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import CursorResult, text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

from tests.rls.conftest import RlsAs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_authenticated_can_read(rls_as: RlsAs, existing_super_admin: PlatformUser) -> None:
    async with rls_as(existing_super_admin.id) as s:
        rows = (await s.execute(text("SELECT signups_enabled FROM platform_settings"))).all()
        assert len(rows) == 1


async def test_non_super_admin_update_silently_blocked(
    rls_as: RlsAs, existing_super_admin: PlatformUser
) -> None:
    user_id = uuid4()
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(user_id), "email": f"x-{user_id.hex[:8]}@example.com"},
        )
        await priv.commit()
    try:
        async with rls_as(user_id) as s:
            res = cast(
                "CursorResult[object]",
                await s.execute(
                    text("UPDATE platform_settings SET signups_enabled = true WHERE id = 1")
                ),
            )
            assert res.rowcount == 0  # RLS makes the row invisible to UPDATE
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await priv.commit()


async def test_super_admin_can_update(rls_as: RlsAs, existing_super_admin: PlatformUser) -> None:
    async with rls_as(existing_super_admin.id) as s:
        res = cast(
            "CursorResult[object]",
            await s.execute(
                text("UPDATE platform_settings SET signups_enabled = true WHERE id = 1")
            ),
        )
        assert res.rowcount == 1
    # Reset to default for test isolation.
    async with SessionLocal() as priv:
        await priv.execute(
            text("UPDATE platform_settings SET signups_enabled = false WHERE id = 1")
        )
        await priv.commit()
