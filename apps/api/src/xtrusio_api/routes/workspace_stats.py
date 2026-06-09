"""GET /api/workspaces/{workspace_id}/stats — workspace dashboard metrics.

Base reachability gate: ``workspace.members.read`` (the workspace overview's
nav perm) — 403 otherwise. Per-metric gates layer on top: ``members`` and
``pending_invites`` ride that same ``workspace.members.read``, while
``recent_activity`` requires ``workspace.audit.read``. A metric the caller
can't read is ``null`` (the frontend omits its card) — e.g. a ``read_only`` /
``editor`` member sees members + invites but NOT recent activity.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..core.permissions import has_permission, require_permission
from ..schemas.workspace_stats import WorkspaceStats
from ..services.workspace_stats import get_workspace_stats

router = APIRouter(prefix="/api/workspaces", tags=["workspace-stats"])

# Per-metric permission keys checked for inclusion in the response.
_METRIC_PERMS = (
    "workspace.members.read",
    "workspace.audit.read",
)


@router.get("/{workspace_id}/stats", response_model=WorkspaceStats)
async def get_stats(
    workspace_id: UUID,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceStats:
    await require_permission(db, user.user_id, "workspace.members.read", workspace_id=workspace_id)
    authorized = {
        key
        for key in _METRIC_PERMS
        if await has_permission(db, user.user_id, key, workspace_id=workspace_id)
    }
    return await get_workspace_stats(db, workspace_id=workspace_id, authorized=authorized)
