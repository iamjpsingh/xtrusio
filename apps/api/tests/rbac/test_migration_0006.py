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
