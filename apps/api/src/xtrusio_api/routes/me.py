"""GET /api/me — composite identity for the frontend AuthGuard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..models.platform_user import PlatformUser
from ..models.tenant import Tenant
from ..models.tenant_membership import TenantMembership
from ..schemas.me import MeResponse, PlatformContext, TenantContext

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

    rows = (
        await db.execute(
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == identity.user_id)
            .order_by(Tenant.created_at.desc())
        )
    ).all()
    tenants = [
        TenantContext(id=t.id, slug=t.slug, name=t.name, role=m.role) for m, t in rows
    ]

    # pending_invite — populated in Plan 2B when invite metadata is read from JWT claims.
    return MeResponse(
        user_id=identity.user_id,
        email=identity.email,
        platform=platform,
        tenants=tenants,
        pending_invite=None,
    )
