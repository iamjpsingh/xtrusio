"""GET /api/workspaces/{workspace_id}/members — paginated members list.

Gated by ``workspace.members.read``. The prefix overlaps with
``workspace_role_grants`` (which owns the ``/{user_id}/roles`` sub-path);
both routers coexist because they register distinct sub-paths.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.workspace_member_list import (
    WorkspaceMemberListItemOut,
    WorkspaceMembersPage,
)
from ..services.workspace_members import (
    CannotRemoveOwnerError,
    MemberNotFoundError,
    list_workspace_members,
    remove_workspace_member,
)

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/members",
    tags=["workspace-members"],
)


@router.get("", response_model=WorkspaceMembersPage)
async def list_members(
    workspace_id: UUID,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> WorkspaceMembersPage:
    await require_permission(db, user.user_id, "workspace.members.read", workspace_id=workspace_id)
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_workspace_members(
        db,
        workspace_id=workspace_id,
        cursor=decoded,
        limit=params.effective_limit,
    )
    return WorkspaceMembersPage(
        items=[WorkspaceMemberListItemOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_member(
    workspace_id: UUID,
    user_id: UUID,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Remove a member from the workspace. Gated by ``workspace.members.manage``.

    404 if the target isn't a member; 409 ``cannot_remove_owner`` if the target
    holds the workspace owner system role (owners are protected — demote via the
    owner-only revoke first). The caller owns the commit here (the service does
    not self-commit)."""
    await require_permission(
        db, user.user_id, "workspace.members.manage", workspace_id=workspace_id
    )
    try:
        await remove_workspace_member(
            db,
            actor_id=user.user_id,
            workspace_id=workspace_id,
            target_user_id=user_id,
        )
        await db.commit()
    except MemberNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member_not_found") from e
    except CannotRemoveOwnerError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot_remove_owner") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
