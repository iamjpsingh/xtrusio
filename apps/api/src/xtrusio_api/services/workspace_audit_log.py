"""Workspace audit-log viewer.

Cursor-paginated SELECT on `rbac_audit_log` filtered to `scope='workspace'
AND workspace_id = :wid` so platform-scope events and other workspaces'
events are never visible at this endpoint.

Cursor encoding is identical to `services.platform_audit_log` (the audit
table's id is bigint, not uuid, so the standard core/pagination primitive
doesn't apply). We import the existing helpers rather than duplicate them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .platform_audit_log import _encode_audit_cursor  # reused — same wire format


async def list_workspace_audit_events(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    cursor: tuple[datetime, int] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """Paginated SELECT on `rbac_audit_log` where scope='workspace'
    AND workspace_id = :wid. Ordering: created_at DESC, id DESC."""
    base = (
        "SELECT id, actor_auth_user_id, action, target_type, target_id, "
        "scope, workspace_id, before, after, created_at "
        "FROM rbac_audit_log WHERE scope = 'workspace' AND workspace_id = :wid "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {"wid": str(workspace_id), "ts": ts, "rid": rid, "lim": limit + 1}
        sql = base + (
            "AND (created_at < :ts OR (created_at = :ts AND id < :rid)) "
            "ORDER BY created_at DESC, id DESC LIMIT :lim"
        )
    else:
        params = {"wid": str(workspace_id), "lim": limit + 1}
        sql = base + "ORDER BY created_at DESC, id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_audit_cursor(last["created_at"], int(last["id"]))
        rows = rows[:limit]
    return rows, next_cursor
