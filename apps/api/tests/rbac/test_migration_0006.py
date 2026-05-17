"""Read-only assertions that migration 0006 created the RBAC schema.

Run `make migrate` before this test. These assertions only READ the live
managed DB schema (information_schema / pg_catalog) — no data is written.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")

_TABLES = ("permissions", "roles", "role_permissions", "user_roles", "rbac_audit_log")


async def test_rbac_tables_exist() -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name = ANY(:names)"
                ),
                {"names": list(_TABLES)},
            )
        ).scalars().all()
    assert set(rows) == set(_TABLES)


async def test_rls_enabled_on_rbac_tables() -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT relname FROM pg_class "
                    "WHERE relrowsecurity AND relname = ANY(:names)"
                ),
                {"names": list(_TABLES)},
            )
        ).scalars().all()
    assert set(rows) == set(_TABLES)


async def test_authenticated_has_dml_grants() -> None:
    async with SessionLocal() as s:
        cnt = (
            await s.execute(
                text(
                    "SELECT count(DISTINCT table_name) "
                    "FROM information_schema.role_table_grants "
                    "WHERE grantee='authenticated' AND privilege_type='SELECT' "
                    "AND table_name = ANY(:names)"
                ),
                {"names": list(_TABLES)},
            )
        ).scalar_one()
    assert cnt == len(_TABLES)


async def test_single_super_admin_partial_unique_index_exists() -> None:
    async with SessionLocal() as s:
        exists = (
            await s.execute(
                text(
                    "SELECT 1 FROM pg_indexes "
                    "WHERE indexname = 'user_roles_one_super_admin'"
                )
            )
        ).scalar_one_or_none()
    assert exists == 1


async def test_platform_system_roles_seeded() -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT key FROM roles WHERE scope='platform' AND is_system "
                    "ORDER BY key"
                )
            )
        ).scalars().all()
    assert rows == ["admin", "super_admin"]


async def test_super_admin_role_has_the_fixed_well_known_id() -> None:
    async with SessionLocal() as s:
        rid = (
            await s.execute(
                text("SELECT id FROM roles WHERE scope='platform' AND key='super_admin'")
            )
        ).scalar_one()
    assert str(rid) == "00000000-0000-0000-0000-0000000000a1"


async def test_each_existing_tenant_has_4_workspace_system_roles() -> None:
    async with SessionLocal() as s:
        bad = (
            await s.execute(
                text(
                    "SELECT t.id FROM tenants t "
                    "LEFT JOIN ("
                    "  SELECT workspace_id, count(*) c FROM roles "
                    "  WHERE scope='workspace' AND is_system GROUP BY workspace_id"
                    ") r ON r.workspace_id = t.id "
                    "WHERE COALESCE(r.c,0) <> 4"
                )
            )
        ).scalars().all()
    assert bad == [], f"tenants missing the 4 workspace system roles: {bad}"


async def test_existing_super_admin_backfilled_to_user_roles() -> None:
    async with SessionLocal() as s:
        sa = (
            await s.execute(
                text("SELECT id FROM platform_users WHERE role='super_admin' LIMIT 1")
            )
        ).scalar_one_or_none()
        if sa is None:
            pytest.skip("no real super_admin present; nothing to assert")
        cnt = (
            await s.execute(
                text(
                    "SELECT count(*) FROM user_roles ur "
                    "JOIN roles r ON r.id = ur.role_id "
                    "WHERE ur.auth_user_id = :sa AND r.scope='platform' "
                    "AND r.key='super_admin'"
                ),
                {"sa": sa},
            )
        ).scalar_one()
    assert cnt == 1


async def test_membership_enum_backfilled_to_user_roles() -> None:
    async with SessionLocal() as s:
        missing = (
            await s.execute(
                text(
                    "SELECT m.id FROM tenant_memberships m "
                    "LEFT JOIN roles r ON r.scope='workspace' "
                    "  AND r.workspace_id = m.tenant_id AND r.key = m.role::text "
                    "LEFT JOIN user_roles ur ON ur.auth_user_id = m.user_id "
                    "  AND ur.role_id = r.id AND ur.workspace_id = m.tenant_id "
                    "WHERE ur.id IS NULL"
                )
            )
        ).scalars().all()
    assert missing == [], f"memberships without a user_roles grant: {missing}"


async def test_invites_have_role_id_backfilled() -> None:
    async with SessionLocal() as s:
        for tbl in ("platform_invites", "tenant_invites"):
            col = (
                await s.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name=:t AND column_name='role_id'"
                    ),
                    {"t": tbl},
                )
            ).scalar_one_or_none()
            assert col == 1, f"{tbl}.role_id missing"
            orphans = (
                await s.execute(
                    text(f"SELECT count(*) FROM {tbl} WHERE role IS NOT NULL AND role_id IS NULL")
                )
            ).scalar_one()
            assert orphans == 0, f"{tbl} has rows with role but no role_id"


async def test_interim_rls_policies_present() -> None:
    """Hardening (code-review Minor): assert the P1-interim policy posture."""
    async with SessionLocal() as s:
        rows = dict(
            (
                await s.execute(
                    text(
                        "SELECT policyname, qual FROM pg_policies "
                        "WHERE schemaname='public' AND policyname IN "
                        "('permissions_authenticated_read','roles_authenticated_read',"
                        "'role_permissions_authenticated_read','user_roles_authenticated_read',"
                        "'rbac_audit_log_no_read')"
                    )
                )
            ).all()
        )
    assert set(rows) == {
        "permissions_authenticated_read",
        "roles_authenticated_read",
        "role_permissions_authenticated_read",
        "user_roles_authenticated_read",
        "rbac_audit_log_no_read",
    }
    assert "false" in (rows["rbac_audit_log_no_read"] or "").lower()
