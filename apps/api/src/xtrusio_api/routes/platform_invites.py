"""POST/GET/DELETE /api/platform/users/invites.

Provisioning actions (create + revoke an invite) are ``super_admin``-ONLY —
inviting platform staff is non-delegatable (a platform admin must not be able
to add platform staff). The GET list stays at ``platform.users.invite`` so a
platform admin retains read visibility of pending invites.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user, require_super_admin
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.invite import (
    CreatePlatformInviteRequest,
    PlatformInviteResponse,
    PlatformInvitesPage,
)
from ..services.platform_invites import (
    InviteAlreadyAcceptedError,
    InvitePendingError,
    UnsupportedInviteRoleError,
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
    require_super_admin(user)
    # PAR-D M1: caller-owns-transaction — build the response from the live
    # (pre-commit) ORM row, then commit; roll back on any typed error. PAR-D H5:
    # the invite email is staged in the outbox and sent by the worker, so this
    # path no longer makes a Supabase call (no synchronous email_provider 502).
    try:
        invite = await create_platform_invite(
            db, email=body.email, role=body.role, invited_by=user.user_id
        )
        response = PlatformInviteResponse.model_validate(invite)
        await db.commit()
    except UnsupportedInviteRoleError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported_invite_role") from e
    except UserExistsError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "user_exists") from e
    except InvitePendingError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_pending") from e
    return response


@router.get("", response_model=PlatformInvitesPage)
async def list_invites(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PlatformInvitesPage:
    await require_permission(db, user.user_id, "platform.users.invite")
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_platform_invites(
        db, cursor=decoded, limit=params.effective_limit
    )
    return PlatformInvitesPage(
        items=[PlatformInviteResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke(
    invite_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    require_super_admin(user)
    try:
        await revoke_platform_invite(db, invite_id=invite_id, actor_id=user.user_id)
    except InviteAlreadyAcceptedError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_already_accepted") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
