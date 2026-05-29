"""Platform-users list service.

Backs ``GET /api/platform/users``. Cursor-paginated by ``(created_at, id)``
DESC so the newest-provisioned user is first — matches every other list
endpoint's ordering convention.

The per-user grant projection (``GET /api/platform/users/{user_id}/roles``)
lives in ``services/platform_role_grants.py``; this list only carries a
``granted_role_count`` aggregated from a LEFT JOIN to ``user_roles`` filtered
to ``workspace_id IS NULL`` so workspace grants don't inflate the platform
counter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.pagination import encode_cursor


async def list_platform_users(
    db: AsyncSession,
    *,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """List platform users with their granted-role count.

    Order: ``created_at DESC, id DESC``. Cursor encodes the last returned
    row's ``(created_at, id)`` so the next page resumes deterministically
    even when multiple users share a creation timestamp.

    ``granted_role_count`` counts only platform-scope grants (``workspace_id
    IS NULL``) — workspace grants are projected separately.
    """
    base = """
        SELECT pu.id, pu.email, pu.role, pu.is_active, pu.created_at,
               pu.last_sign_in_at,
               COUNT(ur.id) AS granted_role_count
        FROM platform_users pu
        LEFT JOIN user_roles ur
          ON ur.auth_user_id = pu.id AND ur.workspace_id IS NULL
    """
    group_order = """
        GROUP BY pu.id
        ORDER BY pu.created_at DESC, pu.id DESC
        LIMIT :lim
    """
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {"ts": ts, "rid": str(rid), "lim": limit + 1}
        where = """
            WHERE (pu.created_at, pu.id) < (:ts, :rid)
        """
        sql = base + where + group_order
    else:
        params = {"lim": limit + 1}
        sql = base + group_order
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last["created_at"], UUID(str(last["id"])))
        rows = rows[:limit]
    return rows, next_cursor
