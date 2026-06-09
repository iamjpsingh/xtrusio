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

from ..core import perm_cache
from ..core.audit import write_audit_event
from ..core.pagination import encode_cursor
from ..core.permissions import set_actor


class MemberNotFoundError(LookupError):
    """The (workspace_id, user_id) pair is not in tenant_memberships."""


class CannotRemoveOwnerError(Exception):
    """The target holds the workspace ``owner`` system role and is protected;
    owners cannot be removed via member-remove. Route maps to 409
    ``cannot_remove_owner``."""


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
              AND (tm.created_at, tm.id) < (:ts, :rid)
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


async def remove_workspace_member(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    target_user_id: UUID,
) -> None:
    """Remove ``target_user_id`` from ``workspace_id``: drop their
    workspace-scoped role grants, then their ``tenant_memberships`` row.

    Pre-checks (in order):
      1. target must be a ``tenant_memberships`` member of this workspace
         (else :class:`MemberNotFoundError` -> 404).
      2. target must NOT hold the workspace ``owner`` system role — owners are
         protected (else :class:`CannotRemoveOwnerError` -> 409). To remove an
         owner you must first revoke their owner grant (which is itself
         owner-only and floor-protected).

    The actor GUC is set first (``set_actor``) so the 0013 priv-escalation
    trigger has the acting user when the ``user_roles`` rows are deleted. The
    caller owns the surrounding transaction (no commit here).
    """
    await set_actor(db, actor_id)
    # 1. Membership must exist in this workspace.
    membership = (
        (
            await db.execute(
                text(
                    "SELECT id, role FROM tenant_memberships "
                    "WHERE tenant_id = :w AND user_id = :u LIMIT 1"
                ),
                {"w": str(workspace_id), "u": str(target_user_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if membership is None:
        raise MemberNotFoundError(f"user {target_user_id} not in workspace {workspace_id}")
    # 2. Protect the workspace owner system role — never remove an owner here.
    owner_grant = (
        await db.execute(
            text(
                "SELECT 1 FROM user_roles ur "
                "JOIN roles r ON r.id = ur.role_id "
                "WHERE r.scope='workspace' AND r.workspace_id = :w "
                "AND r.key='owner' AND r.is_system "
                "AND ur.auth_user_id = :u AND ur.workspace_id = :w "
                "LIMIT 1"
            ),
            {"w": str(workspace_id), "u": str(target_user_id)},
        )
    ).first()
    if owner_grant is not None:
        raise CannotRemoveOwnerError()
    # Drop the target's workspace-scoped grants in this workspace, then the
    # membership row. Both keyed on (workspace_id, user) for scope isolation.
    await db.execute(
        text("DELETE FROM user_roles WHERE auth_user_id = :u AND workspace_id = :w"),
        {"u": str(target_user_id), "w": str(workspace_id)},
    )
    await db.execute(
        text("DELETE FROM tenant_memberships WHERE tenant_id = :w AND user_id = :u"),
        {"w": str(workspace_id), "u": str(target_user_id)},
    )
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_member.remove",
        target_type="user",
        target_id=target_user_id,
        scope="workspace",
        workspace_id=workspace_id,
        before={
            "user_id": str(target_user_id),
            "role": str(membership["role"]),
        },
    )
    await perm_cache.invalidate(target_user_id, workspace_id)
