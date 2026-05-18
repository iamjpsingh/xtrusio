"""P2 RLS permission engine — resolver correctness, helper delegation,
RBAC-table perm-aware policies. Run `make migrate` first.

Hygiene: positive super_admin cases use the read-only `existing_super_admin`
fixture; every other principal is an ephemeral @example.com auth.users row
(+ ephemeral user_roles/roles/tenants) torn down in `finally`. No @example.com
row survives a test (mirrors tests/rls/test_platform_settings_rls.py)."""

from __future__ import annotations

from uuid import UUID, uuid4

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


async def test_super_admin_can_select_platform_roles(
    rls_as: RlsAs, existing_super_admin: PlatformUser
) -> None:
    async with rls_as(existing_super_admin.id) as s:
        n = (
            await s.execute(
                text("SELECT count(*) FROM roles WHERE scope='platform'")
            )
        ).scalar_one()
    assert n >= 2  # super_admin + admin system roles visible to a roles.manage holder


async def test_stranger_cannot_select_platform_roles(rls_as: RlsAs) -> None:
    uid = uuid4()
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
        await priv.commit()
    try:
        async with rls_as(uid) as s:
            n = (
                await s.execute(
                    text("SELECT count(*) FROM roles WHERE scope='platform'")
                )
            ).scalar_one()
        assert n == 0  # no platform.roles.manage → RLS hides every platform role
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


async def test_user_sees_only_own_user_roles_rows(rls_as: RlsAs) -> None:
    uid = uuid4()
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
        await priv.commit()
    try:
        async with rls_as(uid) as s:
            # stranger has zero grants and is no RBAC manager → sees no rows,
            # in particular NOT the real super_admin's platform grant.
            n = (await s.execute(text("SELECT count(*) FROM user_roles"))).scalar_one()
        assert n == 0
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


async def test_audit_log_hidden_from_non_auditor(rls_as: RlsAs) -> None:
    uid = uuid4()
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
        await priv.commit()
    try:
        async with rls_as(uid) as s:
            n = (
                await s.execute(text("SELECT count(*) FROM rbac_audit_log"))
            ).scalar_one()
        assert n == 0
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


# --- direct resolver matrix (closes the P2-Task-1 review coverage gap:
# has_workspace_perm + can_manage_role + cross-scope isolation + a
# genuinely-deprecated-but-PRESENT permission). Ephemeral graph, finally-torn.

async def _make_workspace_principal() -> tuple[UUID, UUID]:
    """Ephemeral @example.com user + tenant + its 4 system workspace roles
    (perms wired via reconcile) + an 'owner' grant. Caller MUST teardown."""
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
            text(
                "INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:id)"
            ),
            {"t": str(tid), "s": f"xt-{tid.hex[:8]}", "n": "P2 resolver probe", "id": str(uid)},
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
    from xtrusio_api.rbac.reconcile import reconcile_rbac

    async with SessionLocal() as s:
        await reconcile_rbac(s)
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO user_roles (auth_user_id, role_id, workspace_id) "
                "SELECT :u, r.id, :t FROM roles r "
                "WHERE r.scope='workspace' AND r.workspace_id=:t AND r.key='owner'"
            ),
            {"u": str(uid), "t": str(tid)},
        )
        await priv.commit()
    return uid, tid


async def _teardown_workspace_principal(uid: UUID, tid: UUID) -> None:
    async with SessionLocal() as priv:
        await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
        # role_permissions rows cascade-delete via roles ON DELETE CASCADE
        await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
        await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
        await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
        await priv.commit()


async def test_has_workspace_perm_and_can_manage_role_direct() -> None:
    uid, tid = await _make_workspace_principal()
    try:
        # owner has every workspace perm incl. roles.manage
        assert await _scalar(
            "SELECT has_workspace_perm(:u,:t,'workspace.roles.manage')", u=str(uid), t=str(tid)
        ) is True
        assert await _scalar(
            "SELECT has_workspace_perm(:u,:t,'workspace.members.read')", u=str(uid), t=str(tid)
        ) is True
        # can_manage_role true for that workspace's 'owner' role row
        rid = await _scalar(
            "SELECT id FROM roles WHERE scope='workspace' AND workspace_id=:t AND key='owner'",
            t=str(tid),
        )
        assert await _scalar("SELECT can_manage_role(:u,:r)", u=str(uid), r=str(rid)) is True
    finally:
        await _teardown_workspace_principal(uid, tid)


async def test_cross_scope_isolation(existing_super_admin: PlatformUser) -> None:
    uid, tid = await _make_workspace_principal()
    try:
        # workspace grant must NOT satisfy a platform check...
        assert await _scalar(
            "SELECT has_platform_perm(:u,'platform.roles.manage')", u=str(uid)
        ) is False
        # ...and the real platform super_admin must NOT satisfy a workspace
        # check for an unrelated workspace.
        assert await _scalar(
            "SELECT has_workspace_perm(:u,:t,'workspace.roles.manage')",
            u=str(existing_super_admin.id), t=str(tid),
        ) is False
    finally:
        await _teardown_workspace_principal(uid, tid)


async def test_genuinely_deprecated_present_permission_does_not_grant() -> None:
    """A permission row that EXISTS but is_deprecated=true, attached to a role
    the user holds, must NOT grant (covers the `NOT p.is_deprecated` branch —
    distinct from the unknown-key path in Task 1's test)."""
    uid, tid = await _make_workspace_principal()
    dep_key = f"workspace.zz_dep_{uid.hex[:8]}"
    try:
        async with SessionLocal() as priv:
            await priv.execute(
                text(
                    "INSERT INTO permissions (scope,key,category,description,is_deprecated) "
                    "VALUES ('workspace',:k,'Deprecated','x',true)"
                ),
                {"k": dep_key},
            )
            await priv.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM roles r, permissions p "
                    "WHERE r.scope='workspace' AND r.workspace_id=:t AND r.key='owner' "
                    "AND p.key=:k"
                ),
                {"t": str(tid), "k": dep_key},
            )
            await priv.commit()
        assert await _scalar(
            "SELECT has_workspace_perm(:u,:t,:k)", u=str(uid), t=str(tid), k=dep_key
        ) is False
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM permissions WHERE key=:k"), {"k": dep_key})
            await priv.commit()
        await _teardown_workspace_principal(uid, tid)


async def test_rbac_table_perm_aware_policies_present() -> None:
    """P2 replaced 0006's interim `*_authenticated_read`/`rbac_audit_log_no_read`
    policies with perm-aware ones. Assert the new posture and that the interim
    names are gone (the inverse of the retired P1 hardening test)."""
    new_names = {
        "permissions_read",
        "roles_read",
        "role_permissions_read",
        "user_roles_read",
        "rbac_audit_log_read",
    }
    old_names = {
        "permissions_authenticated_read",
        "roles_authenticated_read",
        "role_permissions_authenticated_read",
        "user_roles_authenticated_read",
        "rbac_audit_log_no_read",
    }
    async with SessionLocal() as s:
        rows = dict(
            (
                await s.execute(
                    text(
                        "SELECT policyname, qual FROM pg_policies "
                        "WHERE schemaname='public' AND tablename IN "
                        "('permissions','roles','role_permissions','user_roles',"
                        "'rbac_audit_log')"
                    )
                )
            ).all()
        )
    present = set(rows)
    assert new_names <= present, f"missing perm-aware policies: {new_names - present}"
    assert not (old_names & present), f"interim policies not retired: {old_names & present}"
    aud = (rows.get("rbac_audit_log_read") or "").lower()
    assert "audit.read" in aud and aud.strip() != "false"
