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

from . import perm_cache


async def set_actor(db: AsyncSession, actor_id: UUID) -> None:
    """Tag the current transaction with the acting user so the 0013
    ``enforce_priv_escalation`` trigger can run its actor-holds-target-perm
    check.

    ``set_config(..., is_local => true)`` scopes the GUC to the surrounding
    transaction (auto-reset at commit/rollback); the PAR-B ``checkin`` listener
    (``core/db.py``) additionally RESETs ``app.actor_id`` when the connection
    returns to the pool, so a read-only route that never commits can't leak the
    actor to the next request.

    PAR-C H9: this is the single shared actor-set — it replaces four identical
    per-service ``_set_actor`` copies whose asymmetry was the finding.
    """
    await db.execute(
        text("SELECT set_config('app.actor_id', :a, true)"),
        {"a": str(actor_id)},
    )


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


async def _db_platform_perms(db: AsyncSession, user_id: UUID) -> list[str]:
    rows = (
        (
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
        )
        .scalars()
        .all()
    )
    return list(rows)


async def effective_platform_perms(db: AsyncSession, user_id: UUID) -> list[str]:
    """Distinct, sorted platform permission keys the user effectively holds.

    Resolves the same catalog/grant graph as `has_platform_perm` (deprecated
    permissions excluded) so `/me` returns exactly what the resolvers would
    authorize. PAR-D M16: consults the Valkey cache first (display-only; the
    authz gate is never cached). Cache errors fall through to the DB.
    """
    cached = await perm_cache.get_platform(user_id)
    if cached is not None:
        return cached
    perms = await _db_platform_perms(db, user_id)
    await perm_cache.set_platform(user_id, perms)
    return perms


async def _db_workspace_perms_batch(
    db: AsyncSession, user_id: UUID, workspace_ids: list[UUID]
) -> dict[UUID, list[str]]:
    if not workspace_ids:
        return {}
    rows = (
        await db.execute(
            text(
                """
                SELECT ur.workspace_id AS wid,
                       array_agg(DISTINCT p.key ORDER BY p.key) AS perm_keys
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                            AND r.scope = 'workspace'
                            AND r.workspace_id = ur.workspace_id
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.auth_user_id = :u
                  AND ur.workspace_id = ANY(:wids)
                  AND p.scope = 'workspace'
                  AND NOT p.is_deprecated
                GROUP BY ur.workspace_id
                """
            ),
            {"u": user_id, "wids": workspace_ids},
        )
    ).all()
    return {row.wid: list(row.perm_keys) for row in rows}


async def effective_workspace_perms_batch(
    db: AsyncSession, user_id: UUID, workspace_ids: list[UUID]
) -> dict[UUID, list[str]]:
    """Effective workspace perms for MANY workspaces in ONE query (PAR-D H6).

    Same catalog/grant graph as :func:`effective_workspace_perms`, grouped by
    ``workspace_id`` so ``/me`` resolves a 50-tenant user in one round trip.
    Workspaces with no effective perms are absent from the returned mapping.

    PAR-D M16: per-workspace Valkey cache. Cache hits short-circuit; misses are
    resolved with one DB query and written back (the no-perm result is cached as
    ``[]`` so an empty workspace doesn't re-query every call). Cache errors fall
    through to the DB transparently.
    """
    if not workspace_ids:
        return {}
    hits = await perm_cache.get_workspaces(user_id, workspace_ids)
    missing = [w for w in workspace_ids if w not in hits]
    if missing:
        db_res = await _db_workspace_perms_batch(db, user_id, missing)
        # Cache every missing workspace, including the no-perm ones as [].
        payload = {w: db_res.get(w, []) for w in missing}
        await perm_cache.set_workspaces(user_id, payload)
        hits = {**hits, **payload}
    # Preserve the "absent = no perms" contract: drop empty lists from the result.
    return {w: p for w, p in hits.items() if p}


async def effective_workspace_perms(
    db: AsyncSession, user_id: UUID, workspace_id: UUID
) -> list[str]:
    """Distinct, sorted workspace permission keys the user holds in `workspace_id`.

    Mirrors `has_workspace_perm` (deprecated permissions excluded). Delegates to
    the batched, cached path so there is a single cache code path (PAR-D M16).
    """
    return (await effective_workspace_perms_batch(db, user_id, [workspace_id])).get(
        workspace_id, []
    )
