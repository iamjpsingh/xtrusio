"""Workspace-members list service.

Backs ``GET /api/workspaces/{wid}/members``. Cursor-paginated by
``(created_at, id)`` DESC on ``tenant_memberships`` (newest-joined first).

LEFT JOIN to ``auth.users`` is intentional: ``tenant_memberships.user_id``
FKs to ``auth.users(id)`` with ON DELETE CASCADE in production, but the
service-level LEFT JOIN protects against any transient state where the auth
row is missing — the schema surfaces ``email = None`` rather than dropping
the row. ``granted_role_count`` is a LEFT JOIN to ``user_roles`` filtered to
this exact workspace so other workspaces' grants don't bleed into the count.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.pagination import encode_cursor


async def list_workspace_members(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """List members of ``workspace_id`` with their granted-role count.

    Order: ``tenant_memberships.created_at DESC, id DESC``. The membership id
    is the cursor's stable tie-breaker.
    """
    base = """
        SELECT tm.user_id, au.email, tm.role,
               tm.created_at AS joined_at, tm.id AS membership_id,
               COUNT(ur.id) AS granted_role_count
        FROM tenant_memberships tm
        LEFT JOIN auth.users au ON au.id = tm.user_id
        LEFT JOIN user_roles ur
          ON ur.auth_user_id = tm.user_id AND ur.workspace_id = :wid
    """
    group_order = """
        GROUP BY tm.id, au.email
        ORDER BY tm.created_at DESC, tm.id DESC
        LIMIT :lim
    """
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {
            "wid": str(workspace_id),
            "ts": ts,
            "rid": str(rid),
            "lim": limit + 1,
        }
        where = """
            WHERE tm.tenant_id = :wid
              AND (tm.created_at < :ts
                   OR (tm.created_at = :ts AND tm.id < :rid))
        """
        sql = base + where + group_order
    else:
        params = {"wid": str(workspace_id), "lim": limit + 1}
        sql = base + "WHERE tm.tenant_id = :wid " + group_order
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last["joined_at"], UUID(str(last["membership_id"])))
        rows = rows[:limit]
    return rows, next_cursor
