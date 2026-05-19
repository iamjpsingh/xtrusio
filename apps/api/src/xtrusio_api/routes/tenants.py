"""GET/POST /api/tenants."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.permissions import require_permission
from ..models.tenant import Tenant, TenantIn, TenantOut

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Tenant]:
    await require_permission(db, user.user_id, "platform.clients.read")
    rows = (await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))).scalars().all()
    return list(rows)


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Tenant:
    await require_permission(db, user.user_id, "platform.clients.manage")
    tenant = Tenant(slug=body.slug, name=body.name, created_by=user.user_id)
    db.add(tenant)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "slug already taken") from e
    await db.refresh(tenant)
    return tenant
