"""tenants RLS — member can SELECT own tenant; super_admin sees all (regression on 0001)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

from tests.rls.conftest import RlsAs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_member_sees_only_their_tenants(rls_as: RlsAs) -> None:
    a_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(a_id), "email": f"m-{a_id.hex[:8]}@example.com"},
        )
        await s.execute(
            text("INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"),
            {"slug": f"own-{a_id.hex[:8]}", "name": "Own", "uid": str(a_id)},
        )
        tid_raw = (
            await s.execute(
                text("SELECT id FROM tenants WHERE slug = :slug"),
                {"slug": f"own-{a_id.hex[:8]}"},
            )
        ).scalar_one()
        tid: UUID = tid_raw if isinstance(tid_raw, UUID) else UUID(str(tid_raw))
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:tid, :uid, 'owner')"
            ),
            {"tid": str(tid), "uid": str(a_id)},
        )
        await s.execute(
            text("INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"),
            {"slug": f"decoy-{a_id.hex[:8]}", "name": "Decoy", "uid": str(a_id)},
        )
        await s.commit()
    try:
        async with rls_as(a_id) as s:
            rows = (await s.execute(text("SELECT slug FROM tenants ORDER BY slug"))).all()
        slugs = {r[0] for r in rows}
        assert f"own-{a_id.hex[:8]}" in slugs
        assert f"decoy-{a_id.hex[:8]}" not in slugs
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text("DELETE FROM tenant_memberships WHERE user_id = :id"),
                {"id": str(a_id)},
            )
            await priv.execute(
                text("DELETE FROM tenants WHERE created_by = :id"),
                {"id": str(a_id)},
            )
            await priv.execute(
                text("DELETE FROM auth.users WHERE id = :id"),
                {"id": str(a_id)},
            )
            await priv.commit()


async def test_super_admin_sees_all_tenants(
    rls_as: RlsAs, super_admin_user: PlatformUser
) -> None:
    decoy_owner = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(decoy_owner), "email": f"dec-{decoy_owner.hex[:8]}@example.com"},
        )
        await s.execute(
            text("INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"),
            {"slug": f"sa-decoy-{decoy_owner.hex[:8]}", "name": "Decoy", "uid": str(decoy_owner)},
        )
        await s.commit()
    try:
        async with rls_as(super_admin_user.id) as s:
            rows = (await s.execute(text("SELECT slug FROM tenants"))).all()
        slugs = {r[0] for r in rows}
        assert f"sa-decoy-{decoy_owner.hex[:8]}" in slugs
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text("DELETE FROM tenants WHERE created_by = :id"),
                {"id": str(decoy_owner)},
            )
            await priv.execute(
                text("DELETE FROM auth.users WHERE id = :id"),
                {"id": str(decoy_owner)},
            )
            await priv.commit()
