"""POST /api/onboarding/tenants — provisions a fresh signup into a new tenant."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..models.tenant_membership import TenantRole
from ..schemas.onboarding import CreatedTenant, CreateTenantRequest, CreateTenantResponse
from ..services.onboarding import AlreadyHasMembershipError, create_tenant_with_owner

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.post("/tenants", response_model=CreateTenantResponse, status_code=status.HTTP_201_CREATED)
async def onboard(
    body: CreateTenantRequest,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateTenantResponse:
    try:
        tenant = await create_tenant_with_owner(
            db, user_id=identity.user_id, workspace_name=body.workspace_name
        )
    except AlreadyHasMembershipError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_has_membership") from e
    return CreateTenantResponse(
        tenant=CreatedTenant(
            id=tenant.id, slug=tenant.slug, name=tenant.name, role=TenantRole.OWNER
        )
    )
