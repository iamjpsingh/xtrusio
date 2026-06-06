"""GET /api/workspaces/{workspace_id}/audit-log — workspace audit viewer.

Gated by `workspace.audit.read` (held by workspace owner; NOT held by the
other system roles per catalog.SYSTEM_ROLE_PERMISSIONS — only `owner` gets
the full `_workspace()` set; `workspace_admin` excludes `workspace.roles.manage`
but still holds `workspace.audit.read`; `editor`/`read_only` hold only
members.read + settings.read, so they 403 here).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from ..core.permissions import require_permission
from ..schemas.audit_log import AuditEventOut, AuditEventsPage
from ..services.platform_audit_log import (
    _decode_audit_cursor,  # intentional reuse: shared cursor wire format across platform + workspace audit-log endpoints
)
from ..services.workspace_audit_log import list_workspace_audit_events

router = APIRouter(prefix="/api/workspaces", tags=["workspace-audit-log"])


@router.get("/{workspace_id}/audit-log", response_model=AuditEventsPage)
async def list_events(
    workspace_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    category: Annotated[str | None, Query()] = None,
) -> AuditEventsPage:
    await require_permission(db, user.user_id, "workspace.audit.read", workspace_id=workspace_id)
    effective_limit = limit if limit > 0 else DEFAULT_LIMIT
    decoded: tuple[datetime, int] | None = None
    if cursor is not None:
        try:
            decoded = _decode_audit_cursor(cursor)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_workspace_audit_events(
        db, workspace_id=workspace_id, cursor=decoded, limit=effective_limit, category=category
    )
    return AuditEventsPage(
        items=[AuditEventOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
