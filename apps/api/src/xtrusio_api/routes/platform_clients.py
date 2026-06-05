"""GET /api/platform/clients/{slug} — platform-scope client detail.

Returns ONE client tenant's info + members for a platform operator who holds
``platform.clients.read`` (PLATFORM scope — no ``workspace_id``), regardless of
whether they are a member of the tenant. This is the read endpoint behind the
per-client detail page so a non-member platform admin (who provisioned but never
joined) sees the client's name/info + members instead of a "limited view".

The cross-tenant read is INTENDED for platform operators and is gated solely by
the platform permission — a caller without ``platform.clients.read`` gets 403
``permission_denied`` and never reaches the service. The route lives on its own
``/api/platform/clients`` prefix so the ``{slug}`` path param can't collide with
the static ``/api/platform/{settings,users,roles,...}`` sub-paths.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.permissions import require_permission
from ..models.tenant_membership import TenantRole
from ..schemas.platform_client_detail import PlatformClientDetail, PlatformClientMember
from ..services.platform_clients import get_client_by_slug, list_client_members

router = APIRouter(prefix="/api/platform/clients", tags=["platform-clients"])


@router.get("/{slug}", response_model=PlatformClientDetail)
async def get_client_detail(
    slug: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformClientDetail:
    await require_permission(db, user.user_id, "platform.clients.read")
    tenant = await get_client_by_slug(db, slug=slug)
    if tenant is None:
        # Sanitized 404 — no slug echo, no distinction from "exists but hidden".
        raise HTTPException(status.HTTP_404_NOT_FOUND, "client not found")
    member_rows = await list_client_members(db, tenant_id=tenant["id"])
    members = [PlatformClientMember.model_validate(r) for r in member_rows]
    owner_email = next(
        (m.email for m in members if m.role == TenantRole.OWNER and m.email is not None),
        None,
    )
    return PlatformClientDetail(
        id=tenant["id"],
        slug=tenant["slug"],
        name=tenant["name"],
        created_at=tenant["created_at"],
        owner_email=owner_email,
        member_count=len(members),
        members=members,
    )
