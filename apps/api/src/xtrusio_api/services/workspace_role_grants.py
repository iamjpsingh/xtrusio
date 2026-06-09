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

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import perm_cache
from ..core.audit import write_audit_event
from ..core.pagination import encode_cursor
from ..core.permissions import set_actor


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


class RoleNotFoundError(LookupError):
    """The role id doesn't exist or isn't a role of this workspace."""


class RoleScopeMismatchError(Exception):
    """Granting/revoking a role whose scope/workspace doesn't match the URL."""


class GrantNotFoundError(LookupError):
    """The user_roles grant id doesn't exist for this (workspace_id, user_id)."""


class PrivilegeEscalationError(Exception):
    """Actor lacks at least one permission contained in the target role."""

    def __init__(self, missing_perm_key: str) -> None:
        super().__init__(f"actor lacks permission: {missing_perm_key}")
        self.missing_perm_key = missing_perm_key


class OwnerFloorError(Exception):
    """Revoking the proposed owner grant would leave the workspace with zero
    owners. A workspace MUST retain at least one active owner grant."""


class OwnerGrantRequiresOwnerError(Exception):
    """Granting the workspace ``owner`` system role requires the actor to
    already be an owner of this workspace. A non-owner (even a workspace_admin
    holding ``workspace.members.manage``) MUST NOT be able to mint a new owner.
    Route maps this to 403 ``owner_grant_requires_owner``."""


class OwnerRevokeRequiresOwnerError(Exception):
    """Revoking a workspace ``owner`` system-role grant requires the actor to
    already be an owner of this workspace. Combined with the ≥1-owner floor,
    this means only an owner can revoke an owner grant (and never the last one),
    so a non-owner cannot demote an owner. Route maps to 403 ``permission_denied``."""


# PAR-C H9: actor-set is shared (core.permissions.set_actor).


async def _actor_is_owner(db: AsyncSession, *, workspace_id: UUID, actor_id: UUID) -> bool:
    """True iff ``actor_id`` holds the workspace ``owner`` system-role grant in
    ``workspace_id``. Mirrors :func:`_count_owner_grants` (``r.key='owner' AND
    r.is_system``) but pinned to one actor — the owner-only gate for granting
    and revoking the owner role."""
    return bool(
        (
            await db.execute(
                text(
                    "SELECT 1 FROM user_roles ur "
                    "JOIN roles r ON r.id = ur.role_id "
                    "WHERE r.scope='workspace' AND r.workspace_id = :w "
                    "AND r.key='owner' AND r.is_system "
                    "AND ur.auth_user_id = :a AND ur.workspace_id = :w "
                    "LIMIT 1"
                ),
                {"w": str(workspace_id), "a": str(actor_id)},
            )
        ).first()
        is not None
    )


async def _load_role(
    db: AsyncSession, *, workspace_id: UUID, role_id: UUID
) -> dict[str, Any] | None:
    row = (
        (
            await db.execute(
                text(
                    "SELECT id, scope, workspace_id, key, name, is_system "
                    "FROM roles WHERE id = :id "
                    "AND scope = 'workspace' AND workspace_id = :wid"
                ),
                {"id": str(role_id), "wid": str(workspace_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def _find_missing_workspace_perm(
    db: AsyncSession, *, actor_id: UUID, workspace_id: UUID, role_id: UUID
) -> str | None:
    """Mirror the 0009 trigger's workspace-scope branch. Return the first perm
    in the target role the actor does NOT hold in this workspace, else None."""
    row = (
        await db.execute(
            text(
                "SELECT p.key FROM role_permissions rp "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :rid "
                "AND NOT has_workspace_perm(:actor, :wid, p.key) "
                "LIMIT 1"
            ),
            {"rid": str(role_id), "actor": str(actor_id), "wid": str(workspace_id)},
        )
    ).first()
    return str(row.key) if row is not None else None


async def _count_owner_grants(db: AsyncSession, *, workspace_id: UUID) -> int:
    return int(
        (
            await db.execute(
                text(
                    "SELECT count(*) FROM user_roles ur "
                    "JOIN roles r ON r.id = ur.role_id "
                    "WHERE r.scope='workspace' AND r.workspace_id = :w "
                    "AND r.key='owner' AND r.is_system "
                    "AND ur.workspace_id = :w"
                ),
                {"w": str(workspace_id)},
            )
        ).scalar_one()
    )


async def grant_workspace_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    target_user_id: UUID,
    role_id: UUID,
) -> dict[str, Any]:
    """Grant role_id to target_user_id within workspace_id.

    Pre-checks (in order):
      1. target_user_id must be a tenant_memberships member of workspace_id
         (else MembershipNotFoundError -> 404).
      2. role_id must be a workspace-scope role belonging to this workspace
         (else RoleNotFoundError -> 404).
      3. actor must hold every perm in the target role under workspace_id
         (else PrivilegeEscalationError -> 403; defense-in-depth by 0009).

    Idempotent + concurrent-safe: uses ``INSERT ... ON CONFLICT DO NOTHING
    RETURNING`` against the ``user_roles`` UNIQUE (auth_user_id, role_id,
    workspace_id) constraint, with a fallback SELECT for the conflict case.
    workspace_id is NOT NULL for workspace grants, so the NULLS-DISTINCT
    trap doesn't apply and the UNIQUE catches concurrent identical grants
    cleanly. Two simultaneous identical grants → one inserts, the other
    falls through to the SELECT and returns the existing row; both callers
    see success.
    """
    await set_actor(db, actor_id)
    await _require_workspace_membership(db, workspace_id=workspace_id, user_id=target_user_id)
    role = await _load_role(db, workspace_id=workspace_id, role_id=role_id)
    if role is None:
        raise RoleNotFoundError(str(role_id))
    missing = await _find_missing_workspace_perm(
        db, actor_id=actor_id, workspace_id=workspace_id, role_id=role_id
    )
    if missing is not None:
        raise PrivilegeEscalationError(missing)
    # Owner-role gate (on TOP of the perm-based priv-esc check): granting the
    # workspace owner system role requires the actor to already be an owner.
    # This is a ROLE check, not a permission check — a workspace_admin holding
    # workspace.members.manage + workspace.roles.manage would otherwise pass the
    # priv-esc check yet must not be able to create a new owner.
    if (
        role["is_system"]
        and role["key"] == "owner"
        and not await _actor_is_owner(db, workspace_id=workspace_id, actor_id=actor_id)
    ):
        raise OwnerGrantRequiresOwnerError()
    inserted = (
        (
            await db.execute(
                text(
                    "INSERT INTO user_roles "
                    "(auth_user_id, role_id, workspace_id, granted_by) "
                    "VALUES (:u, :r, :w, :g) "
                    "ON CONFLICT (auth_user_id, role_id, workspace_id) DO NOTHING "
                    "RETURNING id, auth_user_id, role_id, workspace_id, "
                    "granted_at, granted_by"
                ),
                {
                    "u": str(target_user_id),
                    "r": str(role_id),
                    "w": str(workspace_id),
                    "g": str(actor_id),
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if inserted is not None:
        row = inserted
    else:
        row = (
            (
                await db.execute(
                    text(
                        "SELECT id, auth_user_id, role_id, workspace_id, granted_at, granted_by "
                        "FROM user_roles WHERE auth_user_id = :u AND role_id = :r "
                        "AND workspace_id = :w"
                    ),
                    {"u": str(target_user_id), "r": str(role_id), "w": str(workspace_id)},
                )
            )
            .mappings()
            .one()
        )
    out = dict(row)
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.grant",
        target_type="user_role",
        target_id=UUID(str(out["id"])),
        scope="workspace",
        workspace_id=workspace_id,
        after={
            "auth_user_id": str(out["auth_user_id"]),
            "role_id": str(out["role_id"]),
            "role_key": role["key"],
            "role_name": role["name"],
        },
    )
    await perm_cache.invalidate(target_user_id, workspace_id)  # PAR-D M16
    return {**out, "role_key": role["key"]}


async def revoke_workspace_role_grant(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    grant_id: UUID,
) -> None:
    """Revoke a workspace-scope grant. The lookup is pinned to
    (grant_id, user_id, workspace_id) — passing a grant id from another
    workspace or another user MUST 404 (scope isolation; not polish).

    Pre-checks (in order):
      1. grant exists with the given (id, auth_user_id, workspace_id) and is
         workspace-scope (else GrantNotFoundError -> 404).
      2. actor holds every perm in the role being revoked
         (else PrivilegeEscalationError -> 403).
      3. if the role is the workspace owner system role, revoking this grant
         must leave at least one other active owner grant in this workspace
         (else OwnerFloorError -> 409).
    """
    await set_actor(db, actor_id)
    grant = (
        (
            await db.execute(
                text(
                    "SELECT ur.id, ur.auth_user_id, ur.role_id, ur.workspace_id, "
                    "r.scope, r.key, r.name, r.is_system "
                    "FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                    "WHERE ur.id = :id AND ur.auth_user_id = :u "
                    "AND ur.workspace_id = :w"
                ),
                {"id": str(grant_id), "u": str(user_id), "w": str(workspace_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if grant is None:
        raise GrantNotFoundError(str(grant_id))
    if grant["scope"] != "workspace":
        raise RoleScopeMismatchError(str(grant_id))
    missing = await _find_missing_workspace_perm(
        db,
        actor_id=actor_id,
        workspace_id=workspace_id,
        role_id=UUID(str(grant["role_id"])),
    )
    if missing is not None:
        raise PrivilegeEscalationError(missing)
    # ≥1-owner floor: only matters if this grant is the workspace owner system
    # role. This count-then-delete pre-check is the FRIENDLY guard (clean 409
    # before touching the row), NOT the actual safety net: it has a TOCTOU
    # window. ``workspace_admin`` also holds ``workspace.members.manage`` (it is
    # NOT owner-only), so two admins can each revoke a different owner grant
    # concurrently — both read count=2 here and both proceed. The real
    # serialiser is the 0010 ``trg_user_roles_owner_floor`` BEFORE DELETE
    # trigger, which takes ``SELECT … FOR UPDATE`` on the workspace owner role
    # row and raises ``last_owner`` on the loser (mapped to 409 in the route).
    if grant["is_system"] and grant["key"] == "owner":
        # Owner-role gate: only an owner of this workspace may revoke an owner
        # grant. A non-owner (even a workspace_admin holding the perms) MUST NOT
        # be able to demote an owner (= revoke-owner + grant). Checked BEFORE the
        # floor so a non-owner gets the 403 permission_denied contract, not a 409.
        if not await _actor_is_owner(db, workspace_id=workspace_id, actor_id=actor_id):
            raise OwnerRevokeRequiresOwnerError()
        # KEEP the ≥1-owner floor: even an owner can't revoke the last owner.
        owners = await _count_owner_grants(db, workspace_id=workspace_id)
        if owners <= 1:
            raise OwnerFloorError(str(grant_id))
    await db.execute(
        text(
            "DELETE FROM user_roles WHERE id = :id " "AND auth_user_id = :u AND workspace_id = :w"
        ),
        {"id": str(grant_id), "u": str(user_id), "w": str(workspace_id)},
    )
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.revoke",
        target_type="user_role",
        target_id=grant_id,
        scope="workspace",
        workspace_id=workspace_id,
        before={
            "auth_user_id": str(grant["auth_user_id"]),
            "role_id": str(grant["role_id"]),
            "role_key": grant["key"],
            "role_name": grant["name"],
        },
    )
    await perm_cache.invalidate(user_id, workspace_id)  # PAR-D M16


async def list_workspace_role_grants(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """List workspace-scope grants for one user in this workspace, paginated
    by (granted_at DESC, id DESC)."""
    base = (
        "SELECT ur.id, ur.auth_user_id, ur.workspace_id, ur.role_id, "
        "r.key AS role_key, ur.granted_at, ur.granted_by "
        "FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
        "WHERE ur.auth_user_id = :u AND ur.workspace_id = :w "
        "AND r.scope = 'workspace' AND r.workspace_id = :w "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {
            "u": str(user_id),
            "w": str(workspace_id),
            "ts": ts,
            "rid": str(rid),
            "lim": limit + 1,
        }
        sql = base + (
            "AND (ur.granted_at, ur.id) < (:ts, :rid) "
            "ORDER BY ur.granted_at DESC, ur.id DESC LIMIT :lim"
        )
    else:
        params = {"u": str(user_id), "w": str(workspace_id), "lim": limit + 1}
        sql = base + "ORDER BY ur.granted_at DESC, ur.id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last["granted_at"], UUID(str(last["id"])))
        rows = rows[:limit]
    return rows, next_cursor
