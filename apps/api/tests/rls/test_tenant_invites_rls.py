"""tenant_invites RLS — owner/admin see their tenant's invites; others cannot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.rbac.grants import grant_role
from xtrusio_api.rbac.reconcile import wire_workspace_role_perms

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
        # P3c: the enum fallback is retired. The positive principal (owner)
        # is now visible to is_tenant_owner_or_admin only via a resolver-side
        # user_roles grant — seed the tenant's workspace system roles + wire
        # role_permissions, then grant the `owner` workspace role (P3a/P3b
        # ephemeral pattern). The editor stays grant-less: the pure resolver
        # correctly denies it, exactly the negative case under test. RLS
        # POLICY under test is unchanged.
        await priv.execute(
            text(
                "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
                "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
                "('owner'),('admin'),('editor'),('read_only')) AS v(key) "
                "ON CONFLICT DO NOTHING"
            ),
            {"t": str(tid)},
        )
        await wire_workspace_role_perms(priv, workspace_id=tid)
        await grant_role(
            priv, auth_user_id=owner_id, scope="workspace", key="owner", workspace_id=tid
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
            # FK-safe order: invites, grants & memberships first, then the
            # tenant (its workspace roles + role_permissions cascade via
            # roles.workspace_id ON DELETE CASCADE), then the auth users.
            await priv.execute(
                text("DELETE FROM tenant_invites WHERE tenant_id = :tid"),
                {"tid": str(tid)},
            )
            await priv.execute(
                text("DELETE FROM user_roles WHERE auth_user_id IN (:o, :e)"),
                {"o": str(owner_id), "e": str(editor_id)},
            )
            await priv.execute(
                text("DELETE FROM tenant_memberships WHERE tenant_id = :tid"),
                {"tid": str(tid)},
            )
            await priv.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id = :o"), {"o": str(owner_id)})
            await priv.execute(text("DELETE FROM auth.users WHERE id = :e"), {"e": str(editor_id)})
            await priv.commit()
