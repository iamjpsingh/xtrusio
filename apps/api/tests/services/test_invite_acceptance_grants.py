"""Invite-acceptance also writes the mapped user_roles grant, in addition to
the existing legacy enum row (unchanged): platform 'admin' invite -> a
user_roles platform 'admin' grant; tenant 'editor' invite -> a user_roles
workspace 'editor' grant for that tenant. Ephemeral @example.com users +
pre-created invite rows, FK-safe finally teardown. No super_admin."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.invite_acceptance import _accept_platform, _accept_tenant

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_accept_platform_invite_also_grants_user_role() -> None:
    uid, invite_id = uuid4(), uuid4()
    email = f"x-{uid.hex[:8]}@example.com"
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await priv.execute(
            text(
                "INSERT INTO platform_invites "
                "(id, email, role, invited_by, expires_at, accepted_at, revoked_at) "
                "VALUES (:id, :email, 'admin', :inv, :exp, NULL, NULL)"
            ),
            {
                "id": str(invite_id),
                "email": email,
                "inv": str(uid),
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        await priv.commit()
    try:
        async with SessionLocal() as s:
            out = await _accept_platform(s, user_id=uid, email=email, invite_id=invite_id)
        assert out["kind"] == "platform"
        assert out["role"] == "admin"
        async with SessionLocal() as s:
            # legacy enum row STILL written (behaviour unchanged)
            m = (
                await s.execute(
                    text("SELECT role::text FROM platform_users WHERE id=:u"),
                    {"u": str(uid)},
                )
            ).scalar_one()
            assert m == "admin"
            # NEW: user_roles platform 'admin' grant
            g = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                        "WHERE ur.auth_user_id=:u AND r.scope='platform' "
                        "AND r.workspace_id IS NULL AND r.key='admin'"
                    ),
                    {"u": str(uid)},
                )
            ).scalar_one()
            assert g == 1
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)}
            )
            await priv.execute(text("DELETE FROM platform_users WHERE id=:u"), {"u": str(uid)})
            await priv.execute(
                text("DELETE FROM platform_invites WHERE id=:i"),
                {"i": str(invite_id)},
            )
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


async def test_accept_tenant_invite_also_grants_user_role() -> None:
    uid, tid, invite_id = uuid4(), uuid4(), uuid4()
    email = f"x-{uid.hex[:8]}@example.com"
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await priv.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:id)"),
            {"t": str(tid), "s": f"xt-{tid.hex[:8]}", "n": "P3a invite probe", "id": str(uid)},
        )
        # That tenant's 4 workspace system roles (mirrors 0006's per-tenant seed).
        await priv.execute(
            text(
                "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
                "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
                "('owner'),('admin'),('editor'),('read_only')) AS v(key)"
            ),
            {"t": str(tid)},
        )
        await priv.execute(
            text(
                "INSERT INTO tenant_invites "
                "(id, tenant_id, email, role, invited_by, expires_at) "
                "VALUES (:id, :tid, :email, 'editor', :inv, :exp)"
            ),
            {
                "id": str(invite_id),
                "tid": str(tid),
                "email": email,
                "inv": str(uid),
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        await priv.commit()
    try:
        async with SessionLocal() as s:
            out = await _accept_tenant(s, user_id=uid, email=email, invite_id=invite_id)
        assert out["kind"] == "tenant"
        assert out["role"] == "editor"
        async with SessionLocal() as s:
            # legacy enum row STILL written (behaviour unchanged)
            m = (
                await s.execute(
                    text(
                        "SELECT role::text FROM tenant_memberships "
                        "WHERE user_id=:u AND tenant_id=:t"
                    ),
                    {"u": str(uid), "t": str(tid)},
                )
            ).scalar_one()
            assert m == "editor"
            # NEW: user_roles workspace 'editor' grant for this tenant
            g = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                        "WHERE ur.auth_user_id=:u AND r.scope='workspace' "
                        "AND r.workspace_id=:t AND r.key='editor'"
                    ),
                    {"u": str(uid), "t": str(tid)},
                )
            ).scalar_one()
            assert g == 1
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)}
            )
            await priv.execute(
                text("DELETE FROM tenant_memberships WHERE user_id=:u"),
                {"u": str(uid)},
            )
            await priv.execute(
                text("DELETE FROM tenant_invites WHERE id=:i"), {"i": str(invite_id)}
            )
            await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()
