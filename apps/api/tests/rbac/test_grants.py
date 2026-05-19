"""grant_role(): resolve a roles row by (scope,key[,workspace_id]) and insert
an idempotent user_roles grant. Ephemeral @example.com user + tenant + system
roles, FK-safe finally teardown. No super_admin."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.rbac.grants import grant_role

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_grant_role_workspace_is_idempotent() -> None:
    uid, tid = uuid4(), uuid4()
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": f"x-{uid.hex[:8]}@example.com"},
        )
        await priv.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:id)"),
            {"t": str(tid), "s": f"xt-{tid.hex[:8]}", "n": "P3a grant probe", "id": str(uid)},
        )
        await priv.execute(
            text(
                "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
                "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
                "('owner'),('admin'),('editor'),('read_only')) AS v(key)"
            ),
            {"t": str(tid)},
        )
        await priv.commit()
    try:
        async with SessionLocal() as s:
            await grant_role(s, auth_user_id=uid, scope="workspace", key="owner",
                             workspace_id=tid)
            await s.commit()
        async with SessionLocal() as s:
            await grant_role(s, auth_user_id=uid, scope="workspace", key="owner",
                             workspace_id=tid)
            await s.commit()
        async with SessionLocal() as s:
            n = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                        "WHERE ur.auth_user_id=:u AND r.scope='workspace' "
                        "AND r.workspace_id=:t AND r.key='owner'"
                    ),
                    {"u": str(uid), "t": str(tid)},
                )
            ).scalar_one()
        assert n == 1
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
            await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


async def test_grant_role_unknown_role_raises() -> None:
    async with SessionLocal() as s:
        with pytest.raises(LookupError):
            await grant_role(s, auth_user_id=uuid4(), scope="platform",
                             key="does_not_exist")
