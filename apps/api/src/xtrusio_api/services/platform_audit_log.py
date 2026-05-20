"""Platform audit-log viewer.

Cursor-paginated SELECT on ``rbac_audit_log`` filtered to ``scope='platform'``
so workspace-scope events aren't visible at this endpoint (those belong to
P5's per-workspace viewer).

The core pagination primitive (`core/pagination.py`) encodes ``(created_at, UUID)``
cursors, but ``rbac_audit_log.id`` is a ``bigint``, not a uuid. Rather than
loosen the shared primitive (used by 3 other endpoints), this module ships a
small dedicated encoder/decoder that mirrors the primitive's wire format but
carries an ``int`` row id.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _encode_audit_cursor(created_at: datetime, row_id: int) -> str:
    raw = json.dumps({"t": created_at.isoformat(), "i": row_id}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_audit_cursor(token: str) -> tuple[datetime, int]:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        obj = json.loads(raw)
        return datetime.fromisoformat(obj["t"]), int(obj["i"])
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError("invalid cursor") from e


async def list_platform_audit_events(
    db: AsyncSession,
    *,
    cursor: tuple[datetime, int] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """Paginated SELECT on ``rbac_audit_log`` where ``scope='platform'``.

    Order is ``created_at DESC, id DESC`` (newest first) — matches the
    pagination convention used by `list_platform_roles` and friends. The
    cursor encodes the last returned row's ``(created_at, id)`` so the next
    page resumes deterministically even if multiple events share a timestamp.
    """
    base = (
        "SELECT id, actor_auth_user_id, action, target_type, target_id, "
        "scope, workspace_id, before, after, created_at "
        "FROM rbac_audit_log WHERE scope = 'platform' "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {"ts": ts, "rid": rid, "lim": limit + 1}
        sql = base + (
            "AND (created_at < :ts OR (created_at = :ts AND id < :rid)) "
            "ORDER BY created_at DESC, id DESC LIMIT :lim"
        )
    else:
        params = {"lim": limit + 1}
        sql = base + "ORDER BY created_at DESC, id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_audit_cursor(last["created_at"], int(last["id"]))
        rows = rows[:limit]
    return rows, next_cursor
