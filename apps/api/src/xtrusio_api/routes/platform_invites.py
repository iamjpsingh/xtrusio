"""POST/GET/DELETE /api/platform/users/invites — super_admin only."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.permissions import require_permission
from ..schemas.invite import (
    CreatePlatformInviteRequest,
    PlatformInviteResponse,
    PlatformInvitesPage,
)
from ..services.platform_invites import (
    EmailProviderUnavailableError,
    InviteAlreadyAcceptedError,
    InvitePendingError,
    UserExistsError,
    create_platform_invite,
    list_platform_invites,
    revoke_platform_invite,
)

router = APIRouter(prefix="/api/platform/users/invites", tags=["platform-invites"])


@router.post("", response_model=PlatformInviteResponse, status_code=status.HTTP_201_CREATED)
async def create(
    body: CreatePlatformInviteRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformInviteResponse:
    await require_permission(db, user.user_id, "platform.users.invite")
    try:
        invite = await create_platform_invite(
            db, email=body.email, role=body.role, invited_by=user.user_id
        )
    except UserExistsError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "user_exists") from e
    except InvitePendingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_pending") from e
    except EmailProviderUnavailableError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return PlatformInviteResponse.model_validate(invite)


@router.get("", response_model=PlatformInvitesPage)
async def list_invites(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformInvitesPage:
    await require_permission(db, user.user_id, "platform.users.invite")
    rows = await list_platform_invites(db)
    # next_cursor: pagination not yet implemented (single page, newest 50)
    return PlatformInvitesPage(
        items=[PlatformInviteResponse.model_validate(r) for r in rows], next_cursor=None
    )


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke(
    invite_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await require_permission(db, user.user_id, "platform.users.manage")
    try:
        await revoke_platform_invite(db, invite_id=invite_id)
    except InviteAlreadyAcceptedError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_already_accepted") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
