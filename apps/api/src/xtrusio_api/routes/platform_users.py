"""GET /api/platform/users — paginated platform-users list.

Gated by ``platform.users.read`` (held by both seeded platform system roles).
Sub-paths under ``/api/platform/users/...`` (grant management, invites) are
owned by other routers (``platform_role_grants``, ``platform_invites``); this
router only registers the empty path so static sub-paths still match those
routers regardless of include order.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.platform_user_list import PlatformUserListItemOut, PlatformUsersPage
from ..services.platform_users import list_platform_users

router = APIRouter(prefix="/api/platform/users", tags=["platform-users"])


@router.get("", response_model=PlatformUsersPage)
async def list_users(
    user: Annotated[CurrentUser, Depends(get_current_user)],
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
