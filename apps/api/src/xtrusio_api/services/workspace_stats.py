"""Workspace dashboard stats service.

Backs ``GET /api/workspaces/{workspace_id}/stats``. Computes ONE ``count(*)``
per authorized metric, scoped to ``:wid``. The backend runs as the table owner
(RLS does not constrain it), so the explicit ``tenant_id = :wid`` /
``workspace_id = :wid`` filters ARE the data fence — every count MUST carry it.

Read-only, caller-owns-tx (no commit). The route resolves the authorized perm
set via ``has_permission`` and passes it here.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.workspace_stats import WorkspaceStats


async def _count(db: AsyncSession, sql: str, wid: UUID) -> int:
    """Run a ``:wid``-parameterised ``SELECT count(*)`` and return the scalar."""
    return int((await db.execute(text(sql), {"wid": str(wid)})).scalar_one())


async def get_workspace_stats(
    db: AsyncSession, *, workspace_id: UUID, authorized: set[str]
) -> WorkspaceStats:
    """Assemble the workspace dashboard metrics for an authorized perm set.

    ``members`` and ``pending_invites`` are gated by ``workspace.members.read``;
    ``recent_activity`` by ``workspace.audit.read``. Every count filters by
    ``:wid`` so another workspace's rows can never leak. The 7-day activity
    window is fixed.
    """
    members: int | None = None
    pending_invites: int | None = None
    recent_activity: int | None = None

    if "workspace.members.read" in authorized:
        members = await _count(
            db,
            "SELECT count(*) FROM tenant_memberships WHERE tenant_id = :wid",
            workspace_id,
        )
        pending_invites = await _count(
            db,
            "SELECT count(*) FROM tenant_invites "
            "WHERE tenant_id = :wid "
            "AND accepted_at IS NULL "
            "AND revoked_at IS NULL "
            "AND expires_at > now()",
            workspace_id,
        )
    if "workspace.audit.read" in authorized:
        recent_activity = await _count(
            db,
            "SELECT count(*) FROM rbac_audit_log "
            "WHERE scope = 'workspace' "
            "AND workspace_id = :wid "
            "AND created_at > now() - interval '7 days'",
            workspace_id,
        )

    return WorkspaceStats(
        members=members,
        pending_invites=pending_invites,
        recent_activity=recent_activity,
    )
