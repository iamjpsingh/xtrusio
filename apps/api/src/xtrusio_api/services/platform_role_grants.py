"""Platform-role grant/revoke service.

Authorization gate (``platform.users.manage``) is the caller's responsibility
(applied at the route layer via ``require_permission``). This service enforces
the governance rules from spec section 6:

- 6.1 privilege-escalation guard: actor must hold every perm in the target role.
  The DB trigger from 0009 enforces this when ``granted_by IS NOT NULL``; the
  service pre-checks for a friendly 403.
- 6.2 single-super_admin invariant: only one active super_admin grant may exist.
  The DB has a partial unique index from 0006 (``user_roles_one_super_admin``);
  the service pre-checks for a friendly 409.

Every grant/revoke writes an audit event in the same tx as the mutation.
The caller owns the transaction (no commit here) — matches the established
service-layer convention used by ``platform_roles.create_platform_role``,
``invite_acceptance``, etc.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import write_audit_event
from ..core.pagination import encode_cursor


class PlatformUserNotFoundError(LookupError):
    """The target platform user id doesn't exist."""


class RoleNotFoundError(LookupError):
    """The role id doesn't exist."""


class RoleScopeMismatchError(Exception):
    """Granting/revoking a non-platform-scope role on a platform user — not
    allowed at the platform-grant endpoint."""


class PrivilegeEscalationError(Exception):
    """Actor lacks at least one permission contained in the target role."""

    def __init__(self, missing_perm_key: str) -> None:
        super().__init__(f"actor lacks permission: {missing_perm_key}")
        self.missing_perm_key = missing_perm_key


class SingleSuperAdminError(Exception):
    """A super_admin grant already exists — invariant violated."""


class GrantNotFoundError(LookupError):
    """The user_roles grant id doesn't exist."""


# --- helpers ---------------------------------------------------------------


async def _set_actor(db: AsyncSession, actor_id: UUID) -> None:
    """Tag the tx with the actor so the DB priv-escalation trigger sees it.

    Set-local (third arg = true) so it auto-resets at tx end.
    """
    await db.execute(
        text("SELECT set_config('app.actor_id', :a, true)"),
        {"a": str(actor_id)},
    )


async def _load_platform_user(db: AsyncSession, user_id: UUID) -> dict[str, Any] | None:
    row = (
        (
            await db.execute(
                text("SELECT id, email, is_active FROM platform_users WHERE id = :id"),
                {"id": str(user_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def _load_role(db: AsyncSession, role_id: UUID) -> dict[str, Any] | None:
    row = (
        (
            await db.execute(
                text(
                    "SELECT id, scope, workspace_id, key, name, is_system "
                    "FROM roles WHERE id = :id"
                ),
                {"id": str(role_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def _find_missing_perm(
    db: AsyncSession, *, actor_id: UUID, role_id: UUID, scope: str
) -> str | None:
    """Return the first perm-key in the target role the actor does NOT hold,
    or None if the actor holds every perm. Mirrors the DB trigger logic so the
    service can return a clean 403 before the DB raises.

    Only platform-scope is implemented today: the service surface here only
    accepts platform-scope grants/revokes. If a future caller needs workspace
    scope checks, plumb ``workspace_id`` through and use ``has_workspace_perm``.
    """
    if scope != "platform":
        return None
    row = (
        await db.execute(
            text(
                "SELECT p.key FROM role_permissions rp "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :rid "
                "AND NOT has_platform_perm(:actor, p.key) "
                "LIMIT 1"
            ),
            {"rid": str(role_id), "actor": str(actor_id)},
        )
    ).first()
    return str(row.key) if row is not None else None


# --- public surface --------------------------------------------------------


async def grant_platform_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    target_user_id: UUID,
    role_id: UUID,
) -> dict[str, Any]:
    """Grant ``role_id`` to ``target_user_id`` on the platform scope.

    Enforces 6.1 priv-escalation + 6.2 single-super_admin before INSERTing.
    Returns the new (or pre-existing, on conflict) grant row including the
    role key.
    """
    await _set_actor(db, actor_id)
    target_user = await _load_platform_user(db, target_user_id)
    if target_user is None:
        raise PlatformUserNotFoundError(str(target_user_id))
    role = await _load_role(db, role_id)
    if role is None:
        raise RoleNotFoundError(str(role_id))
    if role["scope"] != "platform" or role["workspace_id"] is not None:
        raise RoleScopeMismatchError(f"role {role_id} is not a platform-scope role")
    # Single-super_admin check (only for the super_admin system role).
    if role["key"] == "super_admin" and role["is_system"]:
        existing_count = (
            await db.execute(
                text(
                    "SELECT count(*) FROM user_roles ur "
                    "JOIN roles r ON r.id = ur.role_id "
                    "WHERE r.key = 'super_admin' AND r.is_system "
                    "AND r.scope = 'platform'"
                )
            )
        ).scalar_one()
        if existing_count and int(existing_count) >= 1:
            raise SingleSuperAdminError()
    # Privilege-escalation pre-check (friendly 403 before DB trigger fires).
    missing = await _find_missing_perm(db, actor_id=actor_id, role_id=role_id, scope="platform")
    if missing is not None:
        raise PrivilegeEscalationError(missing)
    # Idempotency: the user_roles UNIQUE (auth_user_id, role_id, workspace_id)
    # constraint is NULLS DISTINCT (Postgres default), so ON CONFLICT cannot
    # detect a duplicate when workspace_id IS NULL (the platform-scope case).
    # We pre-check explicitly instead. granted_by = actor_id below makes the
    # DB trigger enforce defense-in-depth on the INSERT path.
    existing = (
        (
            await db.execute(
                text(
                    "SELECT id, auth_user_id, role_id, granted_at, granted_by "
                    "FROM user_roles WHERE auth_user_id = :u AND role_id = :r "
                    "AND workspace_id IS NULL"
                ),
                {"u": str(target_user_id), "r": str(role_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        row = existing
    else:
        # C5/M3: the count pre-check above has a TOCTOU window — two concurrent
        # super_admin grants can both pass it, then both INSERT. The 0006
        # single-super_admin partial unique index (``user_roles_one_super_admin``)
        # rejects the second at the DB; catch that race-to-500 and surface the
        # same 409 the pre-check would have.
        try:
            row = (
                (
                    await db.execute(
                        text(
                            "INSERT INTO user_roles "
                            "(auth_user_id, role_id, workspace_id, granted_by) "
                            "VALUES (:u, :r, NULL, :g) "
                            "RETURNING id, auth_user_id, role_id, granted_at, granted_by"
                        ),
                        {
                            "u": str(target_user_id),
                            "r": str(role_id),
                            "g": str(actor_id),
                        },
                    )
                )
                .mappings()
                .one()
            )
        except IntegrityError as e:
            if "user_roles_one_super_admin" in str(e.orig):
                raise SingleSuperAdminError() from e
            raise
    out = dict(row)
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_role.grant",
        target_type="user_role",
        target_id=UUID(str(out["id"])),
        scope="platform",
        after={
            "auth_user_id": str(out["auth_user_id"]),
            "role_id": str(out["role_id"]),
            "role_key": role["key"],
        },
    )
    return {**out, "role_key": role["key"]}


async def revoke_platform_role_grant(
    db: AsyncSession,
    *,
    actor_id: UUID,
    user_id: UUID,
    grant_id: UUID,
) -> None:
    """Revoke a grant by its id.

    Enforces priv-escalation against the role being revoked (so a non-super_admin
    can't strip super_admin from someone). Audit row is written with ``before=``
    payload describing the deleted grant.

    Validates ``grant.auth_user_id == user_id`` for scope consistency: a request
    addressing user A's path with grant B's id (where B belongs to user C) must
    not succeed. Mismatches return GrantNotFoundError so we don't leak existence.
    """
    await _set_actor(db, actor_id)
    grant = (
        (
            await db.execute(
                text(
                    "SELECT ur.id, ur.auth_user_id, ur.role_id, ur.workspace_id, "
                    "r.scope, r.key, r.is_system "
                    "FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                    "WHERE ur.id = :id"
                ),
                {"id": str(grant_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if grant is None:
        raise GrantNotFoundError(str(grant_id))
    if str(grant["auth_user_id"]) != str(user_id):
        raise GrantNotFoundError(str(grant_id))
    if grant["scope"] != "platform" or grant["workspace_id"] is not None:
        raise RoleScopeMismatchError(f"grant {grant_id} is not a platform-scope grant")
    missing = await _find_missing_perm(
        db, actor_id=actor_id, role_id=UUID(str(grant["role_id"])), scope="platform"
    )
    if missing is not None:
        raise PrivilegeEscalationError(missing)
    await db.execute(text("DELETE FROM user_roles WHERE id = :id"), {"id": str(grant_id)})
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_role.revoke",
        target_type="user_role",
        target_id=grant_id,
        scope="platform",
        before={
            "auth_user_id": str(grant["auth_user_id"]),
            "role_id": str(grant["role_id"]),
            "role_key": grant["key"],
        },
    )


async def list_platform_role_grants(
    db: AsyncSession,
    *,
    user_id: UUID,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """List platform-scope grants for one platform user, paginated by
    ``granted_at DESC, id DESC``."""
    base = (
        "SELECT ur.id, ur.auth_user_id, ur.role_id, r.key AS role_key, "
        "ur.granted_at, ur.granted_by "
        "FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
        "WHERE ur.auth_user_id = :u AND r.scope = 'platform' "
        "AND ur.workspace_id IS NULL "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {
            "u": str(user_id),
            "ts": ts,
            "rid": str(rid),
            "lim": limit + 1,
        }
        sql = base + (
            "AND (ur.granted_at < :ts OR (ur.granted_at = :ts AND ur.id < :rid)) "
            "ORDER BY ur.granted_at DESC, ur.id DESC LIMIT :lim"
        )
    else:
        params = {"u": str(user_id), "lim": limit + 1}
        sql = base + "ORDER BY ur.granted_at DESC, ur.id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last["granted_at"], UUID(str(last["id"])))
        rows = rows[:limit]
    return rows, next_cursor
