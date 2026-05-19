"""Resolver-backed permission checks — the single authz primitive.

Scope is inferred from the key prefix (`platform.` / `workspace.`). Calls the
0007 SECURITY DEFINER resolvers (the single source of truth shared with RLS).
The backend uses the owner DB connection (RLS does not constrain it), so authz
MUST be enforced here explicitly.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def has_permission(
    db: AsyncSession, user_id: UUID, key: str, workspace_id: UUID | None = None
) -> bool:
    scope = key.split(".", 1)[0]
    if scope == "platform":
        return bool(
            (
                await db.execute(
                    text("SELECT has_platform_perm(:u, :k)"),
                    {"u": user_id, "k": key},
                )
            ).scalar_one()
        )
    if scope == "workspace":
        if workspace_id is None:
            return False
        return bool(
            (
                await db.execute(
                    text("SELECT has_workspace_perm(:u, :t, :k)"),
                    {"u": user_id, "t": workspace_id, "k": key},
                )
            ).scalar_one()
        )
    return False


async def require_permission(
    db: AsyncSession, user_id: UUID, key: str, workspace_id: UUID | None = None
) -> None:
    """Raise 403 (detail='permission_denied') unless the user holds `key`."""
    if not await has_permission(db, user_id, key, workspace_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission_denied")


async def effective_platform_perms(db: AsyncSession, user_id: UUID) -> list[str]:
    """Distinct, sorted platform permission keys the user effectively holds.

    Resolves the same catalog/grant graph as `has_platform_perm` (a single
    query, deprecated permissions excluded) so `/me` returns exactly what the
    resolvers would authorize.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT p.key
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                            AND r.scope = 'platform'
                            AND r.workspace_id IS NULL
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.auth_user_id = :u
                  AND ur.workspace_id IS NULL
                  AND p.scope = 'platform'
                  AND NOT p.is_deprecated
                ORDER BY p.key
                """
            ),
            {"u": user_id},
        )
    ).scalars().all()
    return list(rows)


async def effective_workspace_perms(
    db: AsyncSession, user_id: UUID, workspace_id: UUID
) -> list[str]:
    """Distinct, sorted workspace permission keys the user holds in `workspace_id`.

    Mirrors `has_workspace_perm` (single query, deprecated permissions excluded).
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT p.key
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                            AND r.scope = 'workspace'
                            AND r.workspace_id = :t
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.auth_user_id = :u
                  AND ur.workspace_id = :t
                  AND p.scope = 'workspace'
                  AND NOT p.is_deprecated
                ORDER BY p.key
                """
            ),
            {"u": user_id, "t": workspace_id},
        )
    ).scalars().all()
    return list(rows)
