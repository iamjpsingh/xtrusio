"""Audit-log writer for RBAC mutations.

Every RBAC service that mutates `roles`, `role_permissions`, or `user_roles`
calls `write_audit_event(...)` within the same transaction as the mutation.
That guarantees a mutation cannot succeed without its audit row (or vice versa)
— if the audit insert fails, the caller's commit rolls back.

The function does NOT commit; the caller owns the surrounding transaction.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def write_audit_event(
    db: AsyncSession,
    *,
    actor_id: UUID,
    action: str,
    target_type: str,
    target_id: UUID | str,
    scope: str,
    workspace_id: UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Insert one row into rbac_audit_log. Caller owns the surrounding tx.

    ``target_id`` is stored as text (the column is ``String(64)``), so callers
    may pass a non-uuid identifier (e.g. the platform_settings singleton key
    ``"1"``) as well as a :class:`UUID`.
    """
    await db.execute(
        text(
            "INSERT INTO rbac_audit_log "
            "(actor_auth_user_id, action, target_type, target_id, scope, "
            " workspace_id, before, after) "
            "VALUES (:a, :act, :tt, :tid, :s, :w, "
            "        CAST(:b AS jsonb), CAST(:af AS jsonb))"
        ),
        {
            "a": str(actor_id),
            "act": action,
            "tt": target_type,
            "tid": str(target_id),
            "s": scope,
            "w": str(workspace_id) if workspace_id else None,
            "b": _json_or_null(before),
            "af": _json_or_null(after),
        },
    )


def _json_or_null(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    # default=str so UUID/datetime/Decimal serialise; callers should pre-serialise
    # if they need stable ordering.
    return json.dumps(payload, default=str)
