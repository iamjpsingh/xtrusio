"""Workspace-settings get/update service.

Backs ``GET/PUT /api/workspaces/{wid}/settings``. The PUT path writes an
audit row via ``core/audit.write_audit_event`` ONLY when ``name`` actually
changed — no-op writes are not logged (avoids noise in the audit viewer
when a UI re-submits the same value).

Caller owns the transaction (no commit here) — matches every other RBAC
service's convention.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import write_audit_event


class WorkspaceNotFoundError(LookupError):
    """The workspace_id doesn't match any tenants row."""


async def get_workspace_settings(
    db: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    """Return ``{id, slug, name, created_at, updated_at}`` for the workspace.

    Raises :class:`WorkspaceNotFoundError` if the tenant doesn't exist.
    """
    row = (
        (
            await db.execute(
                text(
                    "SELECT id, slug, name, created_at, updated_at " "FROM tenants WHERE id = :id"
                ),
                {"id": str(workspace_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise WorkspaceNotFoundError(str(workspace_id))
    return dict(row)


async def update_workspace_settings(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    name: str,
) -> dict[str, Any]:
    """Update the workspace's ``name``. Writes an audit row with before/after
    only when ``name`` actually changed.

    Raises :class:`WorkspaceNotFoundError` if the tenant doesn't exist.
    """
    existing = await get_workspace_settings(db, workspace_id=workspace_id)
    old_name = str(existing["name"])
    if old_name == name:
        return existing
    updated = (
        (
            await db.execute(
                text(
                    "UPDATE tenants SET name = :n, updated_at = now() "
                    "WHERE id = :id "
                    "RETURNING id, slug, name, created_at, updated_at"
                ),
                {"n": name, "id": str(workspace_id)},
            )
        )
        .mappings()
        .one()
    )
    out = dict(updated)
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace.settings.updated",
        target_type="tenant",
        target_id=workspace_id,
        scope="workspace",
        workspace_id=workspace_id,
        before={"name": old_name},
        after={"name": name},
    )
    return out
