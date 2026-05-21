"""Workspace-role grant/revoke service.

Mirrors `services/platform_role_grants.py` shape, scoped to one workspace.
Authorization gates (`workspace.members.read`/`workspace.members.manage`) are
the caller's responsibility (route layer via `require_permission`). This
service enforces:

- privilege-escalation pre-check against the target role's perms (friendly
  403 before the 0009 DB trigger fires; DB trigger already dispatches to
  has_workspace_perm when workspace_id IS NOT NULL).
- ≥1-active-owner floor: revoking the last workspace `owner` system-role
  grant raises OwnerFloorError (no DB trigger covers this — service-only).
- workspace-scope isolation: every read/write filters on workspace_id, so a
  grant from another workspace cannot be created, listed, or revoked here.

The caller owns the transaction (no commit here).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MembershipNotFoundError(LookupError):
    """The (workspace_id, user_id) pair is not in tenant_memberships."""


async def _require_workspace_membership(
    db: AsyncSession, *, workspace_id: UUID, user_id: UUID
) -> None:
    """Raise MembershipNotFoundError unless (workspace_id, user_id) is in
    tenant_memberships. Grants APIs use this to 404 callers who target a
    non-member — a workspace-role grant for a non-member is meaningless."""
    row = (
        await db.execute(
            text(
                "SELECT 1 FROM tenant_memberships " "WHERE tenant_id = :t AND user_id = :u LIMIT 1"
            ),
            {"t": str(workspace_id), "u": str(user_id)},
        )
    ).first()
    if row is None:
        raise MembershipNotFoundError(f"user {user_id} not in workspace {workspace_id}")
