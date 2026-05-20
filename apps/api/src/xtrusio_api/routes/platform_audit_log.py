"""GET /api/platform/audit-log — platform-scope RBAC audit-log viewer.

Gated by ``platform.audit.read`` (held by both seeded system roles:
``super_admin`` holds every platform perm; ``admin`` holds every platform
perm except ``platform.roles.manage``, so it still holds
``platform.audit.read``). Workspace-scope rows are not visible here —
those belong to P5's per-workspace viewer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from ..core.permissions import require_permission
from ..schemas.audit_log import AuditEventOut, AuditEventsPage
from ..services.platform_audit_log import (
    _decode_audit_cursor,
    list_platform_audit_events,
)

router = APIRouter(prefix="/api/platform/audit-log", tags=["platform-audit-log"])


@router.get("", response_model=AuditEventsPage)
async def list_events(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> AuditEventsPage:
    await require_permission(db, user.user_id, "platform.audit.read")
    effective_limit = limit if limit > 0 else DEFAULT_LIMIT
    decoded: tuple[datetime, int] | None = None
    if cursor is not None:
        try:
            decoded = _decode_audit_cursor(cursor)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_platform_audit_events(db, cursor=decoded, limit=effective_limit)
    return AuditEventsPage(
        items=[AuditEventOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
