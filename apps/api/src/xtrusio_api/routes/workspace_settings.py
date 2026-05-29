"""GET/PUT /api/workspaces/{workspace_id}/settings — workspace settings.

GET gated by ``workspace.settings.read``; PUT gated by
``workspace.settings.manage``. PUT writes an audit row via the service when
``name`` actually changed (no-op updates are not logged).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.permissions import require_permission
from ..schemas.workspace_settings import (
    WorkspaceSettingsOut,
    WorkspaceSettingsUpdate,
)
from ..services.workspace_settings import (
    WorkspaceNotFoundError,
    get_workspace_settings,
    update_workspace_settings,
)

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/settings",
    tags=["workspace-settings"],
)


@router.get("", response_model=WorkspaceSettingsOut)
async def get_workspace_settings_route(
    workspace_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceSettingsOut:
    await require_permission(db, user.user_id, "workspace.settings.read", workspace_id=workspace_id)
    try:
        row = await get_workspace_settings(db, workspace_id=workspace_id)
    except WorkspaceNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workspace_not_found") from e
    return WorkspaceSettingsOut.model_validate(row)


@router.put("", response_model=WorkspaceSettingsOut)
async def put_settings(
    workspace_id: UUID,
    body: WorkspaceSettingsUpdate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceSettingsOut:
    await require_permission(
        db, user.user_id, "workspace.settings.manage", workspace_id=workspace_id
    )
    try:
        row = await update_workspace_settings(
            db, actor_id=user.user_id, workspace_id=workspace_id, name=body.name
        )
        await db.commit()
    except WorkspaceNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workspace_not_found") from e
    return WorkspaceSettingsOut.model_validate(row)
