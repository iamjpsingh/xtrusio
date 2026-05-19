"""POST/GET/DELETE /api/tenants/{tid}/invites — tenant owner/admin."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..schemas.invite import (
    CreateTenantInviteRequest,
    TenantInviteResponse,
    TenantInvitesPage,
)
from ..services.tenant_invites import (
    EmailProviderUnavailableError,
    ForbiddenRoleError,
    InviteAlreadyAcceptedError,
    InvitePendingError,
    NotAMemberError,
    UserAlreadyMemberError,
    create_tenant_invite,
    list_tenant_invites,
    revoke_tenant_invite,
)

router = APIRouter(prefix="/api/tenants/{tenant_id}/invites", tags=["tenant-invites"])


@router.post("", response_model=TenantInviteResponse, status_code=status.HTTP_201_CREATED)
async def create(
    tenant_id: UUID,
    body: CreateTenantInviteRequest,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantInviteResponse:
    try:
        invite = await create_tenant_invite(
            db,
            tenant_id=tenant_id,
            inviter_id=identity.user_id,
            email=body.email,
            role=body.role,
        )
    except NotAMemberError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_a_member") from e
    except ForbiddenRoleError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden_role") from e
    except UserAlreadyMemberError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "user_already_member") from e
    except InvitePendingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_pending") from e
    except EmailProviderUnavailableError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return TenantInviteResponse.model_validate(invite)


@router.get("", response_model=TenantInvitesPage)
async def list_invites(
    tenant_id: UUID,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantInvitesPage:
    try:
        rows = await list_tenant_invites(db, tenant_id=tenant_id, requester_id=identity.user_id)
    except NotAMemberError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_a_member") from e
    # next_cursor: pagination not yet implemented (single page, newest first)
    return TenantInvitesPage(
        items=[TenantInviteResponse.model_validate(r) for r in rows], next_cursor=None
    )


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke(
    tenant_id: UUID,
    invite_id: UUID,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        await revoke_tenant_invite(
            db, tenant_id=tenant_id, invite_id=invite_id, requester_id=identity.user_id
        )
    except NotAMemberError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_a_member") from e
    except InviteAlreadyAcceptedError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_already_accepted") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
