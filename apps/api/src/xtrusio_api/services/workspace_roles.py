"""Workspace-role CRUD service.

Mirrors `services/platform_roles.py` shape, scoped to one workspace.

Authorization gate (`workspace.roles.manage`) is the caller's responsibility
(route layer via `require_permission(..., workspace_id=...)`). This service
enforces immutable-system-roles at the service layer because migration
`0009.reject_system_role_mutation` only blocks scope='platform' system roles —
workspace system role rows (owner/admin/editor/read_only) have is_system=true
but are NOT covered by the DB trigger. The service guard is therefore
load-bearing, not friendly-first.

The caller owns the transaction (no commit here) — matches platform_roles.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import write_audit_event
from ..core.pagination import encode_cursor


class RoleNotFoundError(LookupError):
    """The role id doesn't exist, isn't a workspace role, or belongs to
    another workspace."""


class RoleKeyTakenError(Exception):
    """A workspace role with that key already exists in this workspace."""


class SystemRoleImmutableError(Exception):
    """Caller tried to mutate a workspace system role (owner/admin/editor/
    read_only). Load-bearing — the DB trigger does not block this."""


class UnknownPermissionError(Exception):
    """A permission key is not in the catalog or is deprecated."""


class ScopeMismatchError(Exception):
    """A permission key's scope doesn't match the role's scope."""


# --- helpers ---------------------------------------------------------------


async def _set_actor(db: AsyncSession, actor_id: UUID) -> None:
    await db.execute(
        text("SELECT set_config('app.actor_id', :a, true)"),
        {"a": str(actor_id)},
    )


async def _validate_perm_keys(db: AsyncSession, *, scope: str, keys: list[str]) -> None:
    if not keys:
        return
    rows = (
        await db.execute(
            text(
                "SELECT key, scope FROM permissions " "WHERE key = ANY(:keys) AND NOT is_deprecated"
            ),
            {"keys": keys},
        )
    ).all()
    found = {r.key: r.scope for r in rows}
    missing = set(keys) - set(found)
    if missing:
        raise UnknownPermissionError(f"unknown or deprecated keys: {sorted(missing)}")
    wrong_scope = {k for k, s in found.items() if s != scope}
    if wrong_scope:
        raise ScopeMismatchError(f"keys not in scope={scope!r}: {sorted(wrong_scope)}")


async def _load_role_full(
    db: AsyncSession, *, workspace_id: UUID, role_id: UUID
) -> dict[str, Any] | None:
    """Load one row + aggregated permission_keys, pinning workspace_id."""
    row = (
        (
            await db.execute(
                text(
                    "SELECT r.id, r.key, r.name, r.description, r.is_system, r.scope, "
                    "r.workspace_id, r.created_at, r.updated_at, "
                    "COALESCE(("
                    "  SELECT array_agg(p.key ORDER BY p.key) "
                    "  FROM role_permissions rp "
                    "  JOIN permissions p ON p.id = rp.permission_id "
                    "  WHERE rp.role_id = r.id"
                    "), ARRAY[]::text[]) AS permission_keys "
                    "FROM roles r WHERE r.id = :id "
                    "AND r.scope = 'workspace' AND r.workspace_id = :wid"
                ),
                {"id": str(role_id), "wid": str(workspace_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


# --- public surface --------------------------------------------------------


async def create_workspace_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    key: str,
    name: str,
    description: str | None,
    permission_keys: list[str],
) -> dict[str, Any]:
    """Create a custom (is_system=False) workspace role pinned to workspace_id."""
    await _set_actor(db, actor_id)
    await _validate_perm_keys(db, scope="workspace", keys=permission_keys)
    existing = (
        await db.execute(
            text(
                "SELECT id FROM roles WHERE scope='workspace' "
                "AND workspace_id = :wid AND key = :k"
            ),
            {"wid": str(workspace_id), "k": key},
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise RoleKeyTakenError(key)
    row = (
        (
            await db.execute(
                text(
                    "INSERT INTO roles (scope, workspace_id, key, name, description, "
                    "is_system, created_by) "
                    "VALUES ('workspace', :wid, :key, :name, "
                    "COALESCE(:desc, ''), false, :actor) "
                    "RETURNING id"
                ),
                {
                    "wid": str(workspace_id),
                    "key": key,
                    "name": name,
                    "desc": description,
                    "actor": str(actor_id),
                },
            )
        )
        .mappings()
        .one()
    )
    role_id = UUID(str(row["id"]))
    if permission_keys:
        await db.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT :rid, p.id FROM permissions p "
                "WHERE p.key = ANY(:keys)"
            ),
            {"rid": str(role_id), "keys": permission_keys},
        )
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.create",
        target_type="role",
        target_id=role_id,
        scope="workspace",
        workspace_id=workspace_id,
        after={
            "key": key,
            "name": name,
            "description": description,
            "permission_keys": sorted(permission_keys),
        },
    )
    out = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    assert out is not None
    return out


async def list_workspace_roles(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """Cursor-paginated list of ALL workspace roles in this workspace
    (system + custom)."""
    base = (
        "SELECT r.id, r.key, r.name, r.description, r.is_system, r.scope, "
        "r.workspace_id, r.created_at, r.updated_at, "
        "COALESCE((SELECT array_agg(p.key ORDER BY p.key) "
        "FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
        "WHERE rp.role_id = r.id), ARRAY[]::text[]) AS permission_keys "
        "FROM roles r WHERE r.scope='workspace' AND r.workspace_id = :wid "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {"wid": str(workspace_id), "ts": ts, "rid": str(rid), "lim": limit + 1}
        sql = base + (
            "AND (r.created_at, r.id) < (:ts, :rid) "
            "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
        )
    else:
        params = {"wid": str(workspace_id), "lim": limit + 1}
        sql = base + "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last["created_at"], UUID(str(last["id"])))
        rows = rows[:limit]
    return rows, next_cursor


async def get_workspace_role(
    db: AsyncSession, *, workspace_id: UUID, role_id: UUID
) -> dict[str, Any]:
    row = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    if row is None:
        raise RoleNotFoundError(str(role_id))
    return row


async def update_workspace_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    role_id: UUID,
    name: str | None,
    description: str | None,
    permission_keys: list[str] | None,
) -> dict[str, Any]:
    """Update a custom workspace role. System roles raise SystemRoleImmutableError."""
    await _set_actor(db, actor_id)
    existing = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    if existing is None:
        raise RoleNotFoundError(str(role_id))
    if existing["is_system"]:
        raise SystemRoleImmutableError(str(role_id))
    before = {
        "name": existing["name"],
        "description": existing["description"],
        "permission_keys": list(existing["permission_keys"]),
    }
    if permission_keys is not None:
        await _validate_perm_keys(db, scope="workspace", keys=permission_keys)
    # PAR-D L3: single UPDATE for both fields (one updated_at, one row touch).
    if name is not None or description is not None:
        await db.execute(
            text(
                "UPDATE roles SET name = COALESCE(:n, name), "
                "description = COALESCE(:d, description), updated_at = now() WHERE id = :id"
            ),
            {"n": name, "d": description, "id": str(role_id)},
        )
    if permission_keys is not None:
        await db.execute(
            text("DELETE FROM role_permissions WHERE role_id = :rid"),
            {"rid": str(role_id)},
        )
        if permission_keys:
            await db.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT :rid, p.id FROM permissions p WHERE p.key = ANY(:keys)"
                ),
                {"rid": str(role_id), "keys": permission_keys},
            )
    after_row = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    assert after_row is not None
    after = {
        "name": after_row["name"],
        "description": after_row["description"],
        "permission_keys": list(after_row["permission_keys"]),
    }
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.update",
        target_type="role",
        target_id=role_id,
        scope="workspace",
        workspace_id=workspace_id,
        before=before,
        after=after,
    )
    return after_row


async def delete_workspace_role(
    db: AsyncSession, *, actor_id: UUID, workspace_id: UUID, role_id: UUID
) -> None:
    """Delete a custom workspace role. Cascades to role_permissions and
    user_roles via 0006 ON DELETE CASCADE. System roles raise."""
    await _set_actor(db, actor_id)
    existing = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    if existing is None:
        raise RoleNotFoundError(str(role_id))
    if existing["is_system"]:
        raise SystemRoleImmutableError(str(role_id))
    await db.execute(text("DELETE FROM roles WHERE id = :id"), {"id": str(role_id)})
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.delete",
        target_type="role",
        target_id=role_id,
        scope="workspace",
        workspace_id=workspace_id,
        before={
            "key": existing["key"],
            "name": existing["name"],
            "description": existing["description"],
            "permission_keys": list(existing["permission_keys"]),
        },
    )
