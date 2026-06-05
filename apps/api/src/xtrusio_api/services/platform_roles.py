"""Platform-role CRUD service.

Every mutation:
1. SETs ``app.actor_id`` in the surrounding tx so the DB priv-escalation
   trigger sees the actor (mainly matters for grant/revoke, but we set it
   uniformly for consistency).
2. Writes an audit event via :func:`core.audit.write_audit_event` in the
   SAME transaction as the mutation, so either both land or both roll back.

Authorization gate (``platform.roles.manage``) is the caller's responsibility
(applied at the route layer via ``require_permission``). This service does NOT
re-check the gate — but it DOES enforce immutable-system-roles at the service
layer as a friendlier 422 path before the DB trigger fires.

The caller owns the transaction (no commit here) — matches the established
service-layer convention used by ``grant_role``, ``create_platform_invite``,
etc.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import write_audit_event
from ..core.pagination import encode_cursor
from ..core.permissions import set_actor


class RoleNotFoundError(LookupError):
    """The role id doesn't exist (or isn't a platform role)."""


class RoleKeyTakenError(Exception):
    """A platform role with that key already exists."""


class SystemRoleImmutableError(Exception):
    """Caller tried to mutate a platform system role."""


class UnknownPermissionError(Exception):
    """A permission key is not in the catalog or is deprecated."""


class ScopeMismatchError(Exception):
    """A permission key's scope doesn't match the role's scope."""


class PrivilegeEscalationError(Exception):
    """Actor tried to put a permission they do NOT themselves hold into a role
    definition (create or edit). Mirrors the grant-path guard: you cannot grant
    — or bake into a role — a permission you lack.

    The missing perm key is kept on the exception for server-side logging ONLY;
    the route sanitizes the response body (PAR-A M22) so the RBAC graph can't be
    enumerated by probing."""

    def __init__(self, missing_perm_key: str) -> None:
        super().__init__(f"actor lacks permission: {missing_perm_key}")
        self.missing_perm_key = missing_perm_key


# --- helpers ---------------------------------------------------------------
# PAR-C H9: actor-set is shared (core.permissions.set_actor).


async def _find_missing_perm(db: AsyncSession, *, actor_id: UUID, keys: list[str]) -> str | None:
    """Return the first key in ``keys`` the actor does NOT hold on the platform
    scope, or ``None`` if the actor holds every one.

    This is the role-DEFINITION analogue of the grant path's
    ``platform_role_grants._find_missing_perm``: that helper checks an existing
    role's ``role_permissions`` rows; here the keys are the *requested* resulting
    permission set (not yet — or about to be — written), so we resolve them via
    ``unnest`` against the SAME ``has_platform_perm`` SECURITY DEFINER resolver
    the grant path and the 0013 trigger use. super_admin holds every platform
    perm, so it passes trivially.
    """
    if not keys:
        return None
    row = (
        await db.execute(
            text(
                "SELECT k FROM unnest(CAST(:keys AS text[])) AS k "
                "WHERE NOT has_platform_perm(:actor, k) "
                "LIMIT 1"
            ),
            {"keys": keys, "actor": str(actor_id)},
        )
    ).first()
    return str(row.k) if row is not None else None


async def _validate_perm_keys(db: AsyncSession, *, scope: str, keys: list[str]) -> None:
    """All keys must exist in ``permissions``, be non-deprecated, and match scope."""
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


async def _load_role_full(db: AsyncSession, role_id: UUID) -> dict[str, Any] | None:
    """Load one role row + aggregated permission_keys (sorted)."""
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
                    "FROM roles r WHERE r.id = :id"
                ),
                {"id": str(role_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


# --- public surface --------------------------------------------------------


async def create_platform_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    key: str,
    name: str,
    description: str | None,
    permission_keys: list[str],
) -> dict[str, Any]:
    """Create a custom (``is_system=False``) platform role."""
    await set_actor(db, actor_id)
    await _validate_perm_keys(db, scope="platform", keys=permission_keys)
    # Privilege-escalation guard: the resulting permission set must be a subset
    # of the actor's own effective platform perms. Closes the role-definition
    # escalation hole (an actor with only ``platform.roles.manage`` could
    # otherwise mint a role carrying perms they don't hold and self-assign it).
    # The 0013 trigger only fires on ``user_roles``, never ``role_permissions``,
    # so this service check is the PRIMARY gate for this path.
    missing = await _find_missing_perm(db, actor_id=actor_id, keys=permission_keys)
    if missing is not None:
        raise PrivilegeEscalationError(missing)
    # Friendly-first uniqueness check (DB also has a UNIQUE index).
    existing = (
        await db.execute(
            text(
                "SELECT id FROM roles WHERE scope='platform' "
                "AND workspace_id IS NULL AND key = :k"
            ),
            {"k": key},
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise RoleKeyTakenError(key)
    # Insert role.
    row = (
        (
            await db.execute(
                text(
                    "INSERT INTO roles (scope, workspace_id, key, name, description, "
                    "is_system, created_by) "
                    "VALUES ('platform', NULL, :key, :name, "
                    "COALESCE(:desc, ''), false, :actor) "
                    "RETURNING id"
                ),
                {
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
    # Attach permissions.
    if permission_keys:
        await db.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT :rid, p.id FROM permissions p "
                "WHERE p.key = ANY(:keys)"
            ),
            {"rid": str(role_id), "keys": permission_keys},
        )
    # Audit.
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_role.create",
        target_type="role",
        target_id=role_id,
        scope="platform",
        after={
            "key": key,
            "name": name,
            "description": description,
            "permission_keys": sorted(permission_keys),
        },
    )
    out = await _load_role_full(db, role_id)
    assert out is not None  # just inserted
    return out


async def list_platform_roles(
    db: AsyncSession,
    *,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """Cursor-paginated list of ALL platform roles (system + custom)."""
    base = (
        "SELECT r.id, r.key, r.name, r.description, r.is_system, r.scope, "
        "r.workspace_id, r.created_at, r.updated_at, "
        "COALESCE((SELECT array_agg(p.key ORDER BY p.key) "
        "FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
        "WHERE rp.role_id = r.id), ARRAY[]::text[]) AS permission_keys "
        "FROM roles r WHERE r.scope='platform' AND r.workspace_id IS NULL "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {"ts": ts, "rid": str(rid), "lim": limit + 1}
        sql = base + (
            "AND (r.created_at, r.id) < (:ts, :rid) "
            "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
        )
    else:
        params = {"lim": limit + 1}
        sql = base + "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last["created_at"], UUID(str(last["id"])))
        rows = rows[:limit]
    return rows, next_cursor


async def get_platform_role(db: AsyncSession, *, role_id: UUID) -> dict[str, Any]:
    row = await _load_role_full(db, role_id)
    if row is None or row["scope"] != "platform" or row["workspace_id"] is not None:
        raise RoleNotFoundError(str(role_id))
    return row


async def update_platform_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    role_id: UUID,
    name: str | None,
    description: str | None,
    permission_keys: list[str] | None,
) -> dict[str, Any]:
    """Update a custom platform role.

    System roles raise :class:`SystemRoleImmutableError` (friendly 422 path
    before the DB trigger fires). ``None`` for any field means "leave
    unchanged" per the ``PlatformRolePatch`` contract.
    """
    await set_actor(db, actor_id)
    existing = await _load_role_full(db, role_id)
    if existing is None or existing["scope"] != "platform" or existing["workspace_id"] is not None:
        raise RoleNotFoundError(str(role_id))
    if existing["is_system"]:
        raise SystemRoleImmutableError(str(role_id))
    before = {
        "name": existing["name"],
        "description": existing["description"],
        "permission_keys": list(existing["permission_keys"]),
    }
    # Validate perm_keys BEFORE any write.
    if permission_keys is not None:
        await _validate_perm_keys(db, scope="platform", keys=permission_keys)
        # Privilege-escalation guard: evaluate the RESULTING set (the new keys
        # being written), not the delta — an under-privileged actor must not be
        # able to retain OR add perms they lack. Matches the grant-path
        # invariant. ``permission_keys is None`` (name/description-only edits)
        # skips this entirely.
        missing = await _find_missing_perm(db, actor_id=actor_id, keys=permission_keys)
        if missing is not None:
            raise PrivilegeEscalationError(missing)
    # PAR-D L3: single UPDATE for both fields (one updated_at, one row touch).
    # PlatformRolePatch contract: None = "leave unchanged" — COALESCE keeps the
    # existing value. If callers ever need to clear description, add a sentinel.
    if name is not None or description is not None:
        await db.execute(
            text(
                "UPDATE roles SET name = COALESCE(:n, name), "
                "description = COALESCE(:d, description), updated_at = now() WHERE id = :id"
            ),
            {"n": name, "d": description, "id": str(role_id)},
        )
    # Replace permissions if provided.
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
    after_row = await _load_role_full(db, role_id)
    assert after_row is not None
    after = {
        "name": after_row["name"],
        "description": after_row["description"],
        "permission_keys": list(after_row["permission_keys"]),
    }
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_role.update",
        target_type="role",
        target_id=role_id,
        scope="platform",
        before=before,
        after=after,
    )
    return after_row


async def delete_platform_role(db: AsyncSession, *, actor_id: UUID, role_id: UUID) -> None:
    """Delete a custom platform role.

    FK behavior on ``role_permissions.role_id`` and ``user_roles.role_id`` is
    ``ON DELETE CASCADE`` (see migration 0006), so a single ``DELETE FROM
    roles`` cascades cleanly to both child tables. The 0009 immutable-system
    trigger blocks deletion of platform system roles at the DB layer; the
    service-layer guard below is a friendlier 422 path before the trigger
    fires.
    """
    await set_actor(db, actor_id)
    existing = await _load_role_full(db, role_id)
    if existing is None or existing["scope"] != "platform" or existing["workspace_id"] is not None:
        raise RoleNotFoundError(str(role_id))
    if existing["is_system"]:
        raise SystemRoleImmutableError(str(role_id))
    await db.execute(text("DELETE FROM roles WHERE id = :id"), {"id": str(role_id)})
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_role.delete",
        target_type="role",
        target_id=role_id,
        scope="platform",
        before={
            "key": existing["key"],
            "name": existing["name"],
            "description": existing["description"],
            "permission_keys": list(existing["permission_keys"]),
        },
    )
