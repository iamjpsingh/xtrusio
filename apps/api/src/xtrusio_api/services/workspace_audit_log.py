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

from .platform_audit_log import (  # reused — same wire format + filter logic
    _category_filter,
    _encode_audit_cursor,
)


async def list_workspace_audit_events(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    cursor: tuple[datetime, int] | None = None,
    limit: int = 50,
    category: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Paginated SELECT on `rbac_audit_log` where scope='workspace'
    AND workspace_id = :wid. Ordering: created_at DESC, id DESC.

    ``category`` (optional) restricts to the catalog category's action set;
    None/unknown → no filter, empty category → zero rows. The filter ANDs with
    the cursor comparator, so pagination is unaffected."""
    base = (
        "SELECT r.id, r.actor_auth_user_id, u.email AS actor_email, "
        "r.action, r.target_type, r.target_id, r.scope, r.workspace_id, "
        "r.before, r.after, r.created_at "
        "FROM rbac_audit_log r "
        "LEFT JOIN auth.users u ON u.id = r.actor_auth_user_id "
        "WHERE r.scope = 'workspace' AND r.workspace_id = :wid "
    )
    cat_sql, cat_actions = _category_filter(category)
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {"wid": str(workspace_id), "ts": ts, "rid": rid, "lim": limit + 1}
        sql = (
            base
            + cat_sql
            + (
                "AND (r.created_at, r.id) < (:ts, :rid) "
                "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
            )
        )
    else:
        params = {"wid": str(workspace_id), "lim": limit + 1}
        sql = base + cat_sql + "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
    if cat_actions is not None:
        params["actions"] = cat_actions
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_audit_cursor(last["created_at"], int(last["id"]))
        rows = rows[:limit]
    return rows, next_cursor
