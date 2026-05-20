"""reconcile_user_roles_from_enums(): idempotent enum->user_roles backfill.

Step A heals any post-0006/pre-Task-2 tenant (membership row but NO workspace
system role rows): reconcile seeds the 4 system roles + their role_permissions,
then projects the enum membership into a user_roles grant. Step B replays the
0006 enum->user_roles mapping for rows created since the migration. Ephemeral
@example.com users + ephemeral tenants, FK-safe finally teardown. No super_admin.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_reconcile_backfills_enum_membership_idempotently() -> None:
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
            {"t": str(tid), "s": f"xt-{tid.hex[:8]}", "n": "P3a reconcile probe", "id": str(uid)},
        )
        # tenant pre-existed at 0006: its 4 workspace system roles exist.
        await priv.execute(
            text(
                "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
                "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
                "('owner'),('admin'),('editor'),('read_only')) AS v(key)"
            ),
            {"t": str(tid)},
        )
        # enum-only membership created AFTER 0006 -> no auto user_roles grant.
        await priv.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t,:u,'admin')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
        await priv.commit()
    try:
        async with SessionLocal() as s:
            await reconcile_user_roles_from_enums(s)
        async with SessionLocal() as s:  # second call must be a no-op
            await reconcile_user_roles_from_enums(s)
        async with SessionLocal() as s:
            n = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                        "WHERE ur.auth_user_id=:u AND r.scope='workspace' "
                        "AND r.workspace_id=:t AND r.key='admin'"
                    ),
                    {"u": str(uid), "t": str(tid)},
                )
            ).scalar_one()
            assert n == 1
            # read-only invariant: no tenant_memberships row lacks its grant.
            miss = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM tenant_memberships m "
                        "LEFT JOIN roles r ON r.scope='workspace' "
                        "  AND r.workspace_id=m.tenant_id AND r.key=m.role::text "
                        "LEFT JOIN user_roles ur ON ur.auth_user_id=m.user_id "
                        "  AND ur.role_id=r.id AND ur.workspace_id=m.tenant_id "
                        "WHERE ur.id IS NULL"
                    )
                )
            ).scalar_one()
            assert miss == 0
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)}
            )
            await priv.execute(
                text("DELETE FROM tenant_memberships WHERE user_id=:u"), {"u": str(uid)}
            )
            await priv.execute(
                text(
                    "DELETE FROM role_permissions WHERE role_id IN "
                    "(SELECT id FROM roles WHERE workspace_id=:t)"
                ),
                {"t": str(tid)},
            )
            await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


async def test_reconcile_seeds_missing_workspace_role_rows() -> None:
    """Post-0006/pre-Task-2: a tenant with a membership but NO workspace role
    rows. Step A must seed the 4 system roles + perms, then Step B grants."""
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
            {"t": str(tid), "s": f"xt-{tid.hex[:8]}", "n": "P3a no-roles probe", "id": str(uid)},
        )
        # deliberately NO roles rows for this tenant (simulate post-0006 onboard).
        await priv.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t,:u,'admin')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
        await priv.commit()
    try:
        async with SessionLocal() as s:
            await reconcile_user_roles_from_enums(s)
        async with SessionLocal() as s:  # idempotent
            await reconcile_user_roles_from_enums(s)
        async with SessionLocal() as s:
            roles_n = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM roles WHERE scope='workspace' "
                        "AND workspace_id=:t AND is_system"
                    ),
                    {"t": str(tid)},
                )
            ).scalar_one()
            assert roles_n == 4
            perms_n = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM role_permissions rp "
                        "JOIN roles r ON r.id=rp.role_id "
                        "WHERE r.scope='workspace' AND r.workspace_id=:t"
                    ),
                    {"t": str(tid)},
                )
            ).scalar_one()
            assert perms_n > 0
            g = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                        "WHERE ur.auth_user_id=:u AND r.scope='workspace' "
                        "AND r.workspace_id=:t AND r.key='admin'"
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
                text("DELETE FROM tenant_memberships WHERE user_id=:u"), {"u": str(uid)}
            )
            await priv.execute(
                text(
                    "DELETE FROM role_permissions WHERE role_id IN "
                    "(SELECT id FROM roles WHERE workspace_id=:t)"
                ),
                {"t": str(tid)},
            )
            await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()
