"""P2 RLS permission engine — resolver correctness, helper delegation,
RBAC-table perm-aware policies. Run `make migrate` first.

Hygiene: positive super_admin cases use the read-only `existing_super_admin`
fixture; every other principal is an ephemeral @example.com auth.users row
(+ ephemeral user_roles/roles/tenants) torn down in `finally`. No @example.com
row survives a test (mirrors tests/rls/test_platform_settings_rls.py)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

from tests.rls.conftest import RlsAs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _scalar(sql: str, **params: object) -> object:
    async with SessionLocal() as s:
        return (await s.execute(text(sql), params)).scalar_one()


async def _scalar_all(sql: str, **params: object) -> list[object]:
    async with SessionLocal() as s:
        return list((await s.execute(text(sql), params)).scalars().all())


async def test_resolver_functions_exist_and_are_security_definer() -> None:
    rows = await _scalar_all(
        "SELECT proname FROM pg_proc WHERE proname = ANY(:n) AND prosecdef",
        n=["has_platform_perm", "has_workspace_perm", "can_manage_role"],
    )
    assert set(rows) == {"has_platform_perm", "has_workspace_perm", "can_manage_role"}


async def test_existing_super_admin_has_platform_roles_manage(
    existing_super_admin: PlatformUser,
) -> None:
    got = await _scalar(
        "SELECT has_platform_perm(:u, 'platform.roles.manage')",
        u=str(existing_super_admin.id),
    )
    assert got is True


async def test_unknown_user_has_no_platform_perm() -> None:
    got = await _scalar(
        "SELECT has_platform_perm(:u, 'platform.roles.manage')", u=str(uuid4())
    )
    assert got is False


async def test_deprecated_or_unknown_permission_does_not_grant(
    existing_super_admin: PlatformUser,
) -> None:
    got = await _scalar(
        "SELECT has_platform_perm(:u, 'platform.does.not.exist')",
        u=str(existing_super_admin.id),
    )
    assert got is False


async def test_is_super_admin_still_true_for_real_super_admin(
    existing_super_admin: PlatformUser,
) -> None:
    got = await _scalar("SELECT is_super_admin(:u)", u=str(existing_super_admin.id))
    assert got is True


async def test_is_super_admin_false_for_unknown() -> None:
    assert await _scalar("SELECT is_super_admin(:u)", u=str(uuid4())) is False


async def test_owner_admin_member_helpers_behaviour_preserved(rls_as: RlsAs) -> None:
    """Ephemeral tenant + 4 system workspace roles (+ reconcile) + ephemeral
    user granted workspace 'admin'; assert the delegated helpers match the
    documented truth table; FK-safe teardown."""
    uid = uuid4()
    tid = uuid4()
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
                "INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:id)"
            ),
            {"t": str(tid), "s": f"xt-{tid.hex[:8]}", "n": "P2 RLS probe", "id": str(uid)},
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
        from xtrusio_api.rbac.reconcile import reconcile_rbac

        async with SessionLocal() as s:
            await reconcile_rbac(s)
        async with SessionLocal() as priv:
            await priv.execute(
                text(
                    "INSERT INTO user_roles (auth_user_id, role_id, workspace_id) "
                    "SELECT :u, r.id, :t FROM roles r "
                    "WHERE r.scope='workspace' AND r.workspace_id=:t AND r.key='admin'"
                ),
                {"u": str(uid), "t": str(tid)},
            )
            await priv.commit()
        assert await _scalar("SELECT is_tenant_owner_or_admin(:u,:t)", u=str(uid), t=str(tid)) is True
        assert await _scalar("SELECT is_tenant_member(:u,:t)", u=str(uid), t=str(tid)) is True
        assert await _scalar("SELECT is_super_admin(:u)", u=str(uid)) is False
        assert await _scalar("SELECT is_tenant_member(:u,:t)", u=str(uid), t=str(uuid4())) is False
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
            await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()
