"""Service-layer tests for workspace-role grant/revoke.

Test-data hygiene: every helper uses the @example.com convention; `_cleanup.py`
sweeps all @example.com creators (auth.users, platform_users, tenants,
tenant_memberships, user_roles, rbac_audit_log, custom non-system roles).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.workspace_role_grants import (
    MembershipNotFoundError,
    _require_workspace_membership,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_tenant_with_owner() -> tuple[UUID, UUID]:
    """Seed an @example.com auth.user + tenant + tenant_memberships (owner).
    Returns (workspace_id, owner_user_id)."""
    uid, tid = uuid4(), uuid4()
    email = f"wrg-owner-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) " "VALUES (:t,:s,:n,:u)"),
            {
                "t": str(tid),
                "s": f"wrg-{tid.hex[:8]}",
                "n": "WRG tenant",
                "u": str(uid),
            },
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await s.commit()
    return tid, uid


async def test_require_membership_passes_for_member(db_session: AsyncSession) -> None:
    tid, uid = await _seed_tenant_with_owner()
    # Should not raise.
    await _require_workspace_membership(db_session, workspace_id=tid, user_id=uid)


async def test_require_membership_raises_for_non_member(db_session: AsyncSession) -> None:
    tid, _ = await _seed_tenant_with_owner()
    with pytest.raises(MembershipNotFoundError):
        await _require_workspace_membership(db_session, workspace_id=tid, user_id=uuid4())
