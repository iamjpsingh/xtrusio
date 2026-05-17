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
