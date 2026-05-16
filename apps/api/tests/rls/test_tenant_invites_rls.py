"""tenant_invites RLS — owner/admin see their tenant's invites; others cannot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal

from tests.rls.conftest import RlsAs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_editor_cannot_see_invites(rls_as: RlsAs) -> None:
    owner_id = uuid4()
    editor_id = uuid4()
    async with SessionLocal() as priv:
        for uid in (owner_id, editor_id):
            await priv.execute(
                text(
                    "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                    "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                    "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
                    "'authenticated', :email, '', now(), now(), now())"
                ),
                {"id": str(uid), "email": f"u-{uid.hex[:8]}@example.com"},
            )
        await priv.execute(
            text("INSERT INTO tenants (slug, name, created_by) VALUES (:s, :n, :u)"),
            {"s": f"t-{owner_id.hex[:8]}", "n": "T", "u": str(owner_id)},
        )
        tid = (
            await priv.execute(
                text("SELECT id FROM tenants WHERE slug = :s"),
                {"s": f"t-{owner_id.hex[:8]}"},
            )
        ).scalar_one()
        await priv.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES "
                "(:tid, :owner, 'owner'), (:tid, :editor, 'editor')"
            ),
            {"tid": str(tid), "owner": str(owner_id), "editor": str(editor_id)},
        )
        await priv.execute(
            text(
                "INSERT INTO tenant_invites (tenant_id, email, role, invited_by, expires_at) "
                "VALUES (:tid, :e, 'editor', :inv, :exp)"
            ),
            {
                "tid": str(tid),
                "e": "newhire@example.com",
                "inv": str(owner_id),
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        await priv.commit()
    try:
        async with rls_as(editor_id) as s:
            rows = (await s.execute(text("SELECT email FROM tenant_invites"))).all()
            assert rows == []
        async with rls_as(owner_id) as s:
            rows = (await s.execute(text("SELECT email FROM tenant_invites"))).all()
            assert len(rows) == 1
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text("DELETE FROM tenant_invites WHERE tenant_id = :tid"),
                {"tid": str(tid)},
            )
            await priv.execute(
                text("DELETE FROM tenant_memberships WHERE tenant_id = :tid"),
                {"tid": str(tid)},
            )
            await priv.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id = :o"), {"o": str(owner_id)})
            await priv.execute(text("DELETE FROM auth.users WHERE id = :e"), {"e": str(editor_id)})
            await priv.commit()
