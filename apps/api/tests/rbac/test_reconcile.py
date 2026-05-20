"""Reconciler idempotency + soft-deprecation + system-role wiring.

Reads/writes ONLY the catalog-owned tables (permissions / role_permissions for
is_system roles). Never creates users/tenants. Idempotent: safe on the managed
DB (the catalog is the same every run)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.rbac.catalog import CATALOG, SYSTEM_ROLE_PERMISSIONS
from xtrusio_api.rbac.reconcile import reconcile_rbac

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_all_catalog_keys_present_after_reconcile() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
        keys = (await s.execute(text("SELECT key FROM permissions"))).scalars().all()
    for p in CATALOG:
        assert p.key in keys


async def test_reconcile_is_idempotent() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
        n1 = (await s.execute(text("SELECT count(*) FROM permissions"))).scalar_one()
        await reconcile_rbac(s)
        n2 = (await s.execute(text("SELECT count(*) FROM permissions"))).scalar_one()
    assert n1 == n2 == len(CATALOG)


async def test_super_admin_role_has_all_platform_permissions() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
        got = (
            (
                await s.execute(
                    text(
                        "SELECT p.key FROM role_permissions rp "
                        "JOIN roles r ON r.id=rp.role_id "
                        "JOIN permissions p ON p.id=rp.permission_id "
                        "WHERE r.scope='platform' AND r.key='super_admin'"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert set(got) == set(SYSTEM_ROLE_PERMISSIONS["super_admin"])


async def test_workspace_owner_roles_wired_for_every_tenant() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
        bad = (
            (
                await s.execute(
                    text(
                        "SELECT r.id FROM roles r "
                        "WHERE r.scope='workspace' AND r.key='owner' AND r.is_system "
                        "AND (SELECT count(*) FROM role_permissions rp "
                        "     WHERE rp.role_id=r.id) <> :n"
                    ),
                    {"n": len(SYSTEM_ROLE_PERMISSIONS["owner"])},
                )
            )
            .scalars()
            .all()
        )
    assert bad == []


async def test_unknown_db_permission_is_soft_deprecated_not_deleted() -> None:
    # try/finally: this writes the SHARED managed DB. If the assertion fails
    # the synthetic non-catalog row MUST still be removed, else every later
    # reconcile_rbac run perpetually soft-deprecates it and pollutes the
    # catalog table for other tests.
    try:
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO permissions (scope,key,category,description) "
                    "VALUES ('platform','platform.zzz.legacy','Legacy','x') "
                    "ON CONFLICT (key) DO NOTHING"
                )
            )
            await s.commit()
            await reconcile_rbac(s)
            row = (
                await s.execute(
                    text("SELECT is_deprecated FROM permissions " "WHERE key='platform.zzz.legacy'")
                )
            ).scalar_one_or_none()
        assert row is True
    finally:
        async with SessionLocal() as s:
            await s.execute(text("DELETE FROM permissions WHERE key='platform.zzz.legacy'"))
            await s.commit()
