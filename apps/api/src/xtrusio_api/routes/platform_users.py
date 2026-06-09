"""GET /api/platform/users — paginated platform-users list.
POST /api/platform/users — super_admin direct-create a platform user.

GET is gated by ``platform.users.read`` (held by both seeded platform system
roles); POST is ``super_admin``-ONLY (provisioning platform staff is
non-delegatable — a platform admin cannot create platform users). Sub-paths
under
``/api/platform/users/...`` (grant management, invites) are owned by other
routers (``platform_role_grants``, ``platform_invites``); this router only
registers the empty path so static sub-paths still match those routers
regardless of include order.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated, require_super_admin
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.platform_user_create import PlatformUserCreate, PlatformUserCreated
from ..schemas.platform_user_list import PlatformUserListItemOut, PlatformUsersPage
from ..services.platform_user_provision import (
    EmailProviderUnavailableError,
    PlatformUserExistsError,
    create_platform_user,
)
from ..services.platform_users import list_platform_users

router = APIRouter(prefix="/api/platform/users", tags=["platform-users"])


@router.get("", response_model=PlatformUsersPage)
async def list_users(
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PlatformUsersPage:
    await require_permission(db, user.user_id, "platform.users.read")
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_platform_users(db, cursor=decoded, limit=params.effective_limit)
    return PlatformUsersPage(
        items=[PlatformUserListItemOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post("", response_model=PlatformUserCreated, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: PlatformUserCreate,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformUserCreated:
    await require_super_admin(db, user.user_id)
    # PAR-D M1: caller-owns-transaction — the service flushes so a duplicate
    # surfaces here; we commit on success and roll back on any typed error.
    try:
        created = await create_platform_user(
            db, actor_id=user.user_id, email=body.email, password=body.password
        )
        await db.commit()
    except PlatformUserExistsError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "user_exists") from e
    except EmailProviderUnavailableError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return created
