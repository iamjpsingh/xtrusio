"""GET/POST/PATCH/DELETE /api/workspaces/{workspace_id}/roles — workspace owner.

All endpoints gated by `workspace.roles.manage` (which workspace `owner`
holds and `workspace_admin`/`editor`/`read_only` do NOT — see
catalog.SYSTEM_ROLE_PERMISSIONS). The require_permission call passes
`workspace_id=workspace_id` so the resolver dispatches to has_workspace_perm.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.workspace_role import (
    WorkspaceRoleIn,
    WorkspaceRoleOut,
    WorkspaceRolePatch,
    WorkspaceRolesPage,
)
from ..services.workspace_roles import (
    RoleKeyTakenError,
    RoleNotFoundError,
    ScopeMismatchError,
    SystemRoleImmutableError,
    UnknownPermissionError,
    create_workspace_role,
    delete_workspace_role,
    get_workspace_role,
    list_workspace_roles,
    update_workspace_role,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspace-roles"])


@router.get("/{workspace_id}/roles", response_model=WorkspaceRolesPage)
async def list_roles(
    workspace_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> WorkspaceRolesPage:
    await require_permission(db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id)
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_workspace_roles(
        db, workspace_id=workspace_id, cursor=decoded, limit=params.effective_limit
    )
    return WorkspaceRolesPage(
        items=[WorkspaceRoleOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post(
    "/{workspace_id}/roles",
    response_model=WorkspaceRoleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_role(
    workspace_id: UUID,
    body: WorkspaceRoleIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRoleOut:
    await require_permission(db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id)
    try:
        row = await create_workspace_role(
            db,
            actor_id=user.user_id,
            workspace_id=workspace_id,
            key=body.key,
            name=body.name,
            description=body.description,
            permission_keys=body.permission_keys,
        )
        await db.commit()
    except RoleKeyTakenError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "role_key_taken") from e
    except UnknownPermissionError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except ScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return WorkspaceRoleOut.model_validate(row)


@router.get("/{workspace_id}/roles/{role_id}", response_model=WorkspaceRoleOut)
async def get_role(
    workspace_id: UUID,
    role_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRoleOut:
    await require_permission(db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id)
    try:
        row = await get_workspace_role(db, workspace_id=workspace_id, role_id=role_id)
    except RoleNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    return WorkspaceRoleOut.model_validate(row)


@router.patch("/{workspace_id}/roles/{role_id}", response_model=WorkspaceRoleOut)
async def update_role(
    workspace_id: UUID,
    role_id: UUID,
    body: WorkspaceRolePatch,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRoleOut:
    await require_permission(db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id)
    try:
        row = await update_workspace_role(
            db,
            actor_id=user.user_id,
            workspace_id=workspace_id,
            role_id=role_id,
            name=body.name,
            description=body.description,
            permission_keys=body.permission_keys,
        )
        await db.commit()
    except RoleNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    except SystemRoleImmutableError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "system_role_immutable") from e
    except UnknownPermissionError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except ScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return WorkspaceRoleOut.model_validate(row)


@router.delete(
    "/{workspace_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_role(
    workspace_id: UUID,
    role_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await require_permission(db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id)
    try:
        await delete_workspace_role(
            db, actor_id=user.user_id, workspace_id=workspace_id, role_id=role_id
        )
        await db.commit()
    except RoleNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    except SystemRoleImmutableError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "system_role_immutable") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
