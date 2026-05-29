"""POST /api/onboarding/tenants — provisions a fresh signup into a new tenant.

PAR-A H8: rate-limited at 5 req/authenticated-user/hour (legit onboarding is
a one-shot; the limit guards against accidental retries + scripted abuse).

Note: ``from __future__ import annotations`` is intentionally OMITTED here —
SlowAPI's ``functools.wraps`` retains the inner function's annotations, but
FastAPI resolves forward refs via the OUTER wrapper's ``__globals__``
(slowapi.extension), which doesn't see this module's imports.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..core.rate_limit import ONBOARDING_RATE, limiter
from ..models.tenant_membership import TenantRole
from ..schemas.onboarding import CreatedTenant, CreateTenantRequest, CreateTenantResponse
from ..services.onboarding import AlreadyHasMembershipError, create_tenant_with_owner

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


def _user_key_func(request: Request) -> str:
    """Key the onboarding limit by authenticated user id (PAR-A H8)."""
    identity: AuthIdentity | None = getattr(request.state, "identity", None)
    if identity is None:
        # Defensive — the require_authenticated dep should have populated state.
        if request.client is None:
            return "127.0.0.1"
        return request.client.host
    return f"user:{identity.user_id}"


@router.post("/tenants", response_model=CreateTenantResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(ONBOARDING_RATE, key_func=_user_key_func)
async def onboard(
    request: Request,
    body: CreateTenantRequest,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateTenantResponse:
    try:
        tenant = await create_tenant_with_owner(
            db, user_id=identity.user_id, workspace_name=body.workspace_name
        )
        # PAR-D M1: build the response from the live (pre-commit) ORM attributes,
        # then commit. Reading after commit would trip expire-on-commit reloads.
        response = CreateTenantResponse(
            tenant=CreatedTenant(
                id=tenant.id, slug=tenant.slug, name=tenant.name, role=TenantRole.OWNER
            )
        )
        await db.commit()
    except AlreadyHasMembershipError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "already_has_membership") from e
    return response
