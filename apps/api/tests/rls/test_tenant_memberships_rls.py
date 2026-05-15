"""tenant_memberships RLS — self-read, super_admin all, owner/admin manage own tenant."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

from tests.rls.conftest import RlsAs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_tenant_with_owner(name_suffix: str) -> tuple[UUID, UUID]:
    owner_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(owner_id), "email": f"o-{name_suffix}@example.com"},
        )
        await s.execute(
            text("INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"),
            {"slug": f"t-{name_suffix}", "name": f"Tenant {name_suffix}", "uid": str(owner_id)},
        )
        tid_raw = (
            await s.execute(
                text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": f"t-{name_suffix}"}
            )
        ).scalar_one()
        tid: UUID = tid_raw if isinstance(tid_raw, UUID) else UUID(str(tid_raw))
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:tid, :uid, 'owner')"
            ),
            {"tid": str(tid), "uid": str(owner_id)},
        )
        await s.commit()
    return owner_id, tid


async def _cleanup(user_id: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(
            text("DELETE FROM tenant_memberships WHERE user_id = :id"),
            {"id": str(user_id)},
        )
        await s.execute(
            text("DELETE FROM tenants WHERE created_by = :id"),
            {"id": str(user_id)},
        )
        await s.execute(
            text("DELETE FROM auth.users WHERE id = :id"),
            {"id": str(user_id)},
        )
        await s.commit()


async def test_user_sees_own_membership_not_others(rls_as: RlsAs) -> None:
    a_id, _ = await _seed_tenant_with_owner(uuid4().hex[:8])
    b_id, _ = await _seed_tenant_with_owner(uuid4().hex[:8])
    try:
        async with rls_as(a_id) as s:
            rows = (await s.execute(text("SELECT user_id FROM tenant_memberships"))).all()
        seen = {str(r[0]) for r in rows}
        assert str(a_id) in seen
        assert str(b_id) not in seen
    finally:
        await _cleanup(a_id)
        await _cleanup(b_id)


async def test_super_admin_sees_all(rls_as: RlsAs, super_admin_user: PlatformUser) -> None:
    a_id, _ = await _seed_tenant_with_owner(uuid4().hex[:8])
    try:
        async with rls_as(super_admin_user.id) as s:
            rows = (await s.execute(text("SELECT user_id FROM tenant_memberships"))).all()
        seen = {str(r[0]) for r in rows}
        assert str(a_id) in seen
    finally:
        await _cleanup(a_id)
