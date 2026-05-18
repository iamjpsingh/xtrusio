"""Onboarding also creates a user_roles 'owner' grant for the new workspace,
in addition to the existing tenant_memberships(role=OWNER) row (unchanged).
Ephemeral @example.com user; FK-safe teardown."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.onboarding import create_tenant_with_owner

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_onboarding_grants_owner_user_role() -> None:
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
    tid = None
    try:
        async with SessionLocal() as s:
            tenant = await create_tenant_with_owner(
                s, user_id=uid, workspace_name="P3a Onboard Probe"
            )
            tid = tenant.id
        async with SessionLocal() as s:
            # legacy enum row STILL written (behaviour unchanged)
            m = (
                await s.execute(
                    text(
                        "SELECT role::text FROM tenant_memberships "
                        "WHERE user_id=:u AND tenant_id=:t"
                    ),
                    {"u": str(uid), "t": str(tid)},
                )
            ).scalar_one()
            assert m == "owner"
            # NEW: user_roles owner grant for this workspace
            g = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                        "WHERE ur.auth_user_id=:u AND r.scope='workspace' "
                        "AND r.workspace_id=:t AND r.key='owner'"
                    ),
                    {"u": str(uid), "t": str(tid)},
                )
            ).scalar_one()
            assert g == 1
    finally:
        async with SessionLocal() as priv:
            if tid is not None:
                await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
                await priv.execute(text("DELETE FROM tenant_memberships WHERE user_id=:u"), {"u": str(uid)})
                await priv.execute(text("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE workspace_id=:t)"), {"t": str(tid)})
                await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
                await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()
