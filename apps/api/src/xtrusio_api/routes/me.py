"""GET /api/me — composite identity for the frontend AuthGuard."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..core.permissions import effective_platform_perms, effective_workspace_perms
from ..models.platform_invite import PlatformInvite
from ..models.platform_user import PlatformUser
from ..models.tenant import Tenant
from ..models.tenant_invite import TenantInvite
from ..models.tenant_membership import TenantMembership
from ..schemas.me import MeResponse, PendingInvite, PlatformContext, TenantContext

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeResponse)
async def me(
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeResponse:
    pu = (
        await db.execute(select(PlatformUser).where(PlatformUser.id == identity.user_id))
    ).scalar_one_or_none()
    platform = None
    if pu is not None and pu.is_active:
        platform = PlatformContext(role=pu.role, is_active=pu.is_active)

    platform_permissions = await effective_platform_perms(db, identity.user_id)

    rows = (
        await db.execute(
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == identity.user_id)
            .order_by(Tenant.created_at.desc())
        )
    ).all()
    tenants = [
        TenantContext(
            id=t.id,
            slug=t.slug,
            name=t.name,
            role=m.role,
            permissions=await effective_workspace_perms(db, identity.user_id, t.id),
        )
        for m, t in rows
    ]

    pending_invite = None
    # PAR-A C2: prefer ``app_metadata`` (service-role-only writable); fall
    # back to ``user_metadata`` only when ``app_metadata`` doesn't carry the
    # claim (covers in-flight invites issued before the migration).
    md = {**identity.user_metadata, **identity.app_metadata}
    now = datetime.now(UTC)

    def _parse(raw: object) -> UUID | None:
        try:
            return UUID(str(raw))
        except (ValueError, TypeError):
            return None

    if (pid := _parse(md.get("platform_invite_id"))) is not None:
        inv = (
            await db.execute(select(PlatformInvite).where(PlatformInvite.id == pid))
        ).scalar_one_or_none()
        if (
            inv is not None
            and inv.accepted_at is None
            and inv.revoked_at is None
            and inv.expires_at > now
            and inv.email.lower() == identity.email.lower()
        ):
            pending_invite = PendingInvite(
                kind="platform", id=inv.id, tenant_id=None, role=inv.role.value
            )
    elif (tid := _parse(md.get("tenant_invite_id"))) is not None:
        tinv = (
            await db.execute(select(TenantInvite).where(TenantInvite.id == tid))
        ).scalar_one_or_none()
        if (
            tinv is not None
            and tinv.accepted_at is None
            and tinv.revoked_at is None
            and tinv.expires_at > now
            and tinv.email.lower() == identity.email.lower()
        ):
            pending_invite = PendingInvite(
                kind="tenant",
                id=tinv.id,
                tenant_id=tinv.tenant_id,
                role=tinv.role.value,
            )

    return MeResponse(
        user_id=identity.user_id,
        email=identity.email,
        platform=platform,
        platform_permissions=platform_permissions,
        tenants=tenants,
        pending_invite=pending_invite,
    )
