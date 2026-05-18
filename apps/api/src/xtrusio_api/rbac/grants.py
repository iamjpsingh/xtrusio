"""Idempotent user_roles grant helper — the single write path for granting a
role to a principal. Resolves the roles row by (scope, key[, workspace_id])
and inserts user_roles with ON CONFLICT DO NOTHING against the
UNIQUE(auth_user_id, role_id, workspace_id) constraint. Used by onboarding,
invite-acceptance, bootstrap, and the enum→user_roles reconciler.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def grant_role(
    db: AsyncSession,
    *,
    auth_user_id: UUID,
    scope: str,
    key: str,
    workspace_id: UUID | None = None,
    granted_by: UUID | None = None,
) -> None:
    """Grant the (scope, key[, workspace_id]) system role to auth_user_id.

    Idempotent: a duplicate (auth_user_id, role_id, workspace_id) is a no-op.
    Raises LookupError if no matching is_system role exists (caller bug /
    unmapped enum value — must be handled explicitly, never silently).
    The caller owns the surrounding transaction (no commit here).
    """
    role_id = (
        await db.execute(
            text(
                "SELECT id FROM roles "
                "WHERE scope = :scope AND key = :key AND is_system "
                "AND workspace_id IS NOT DISTINCT FROM :wid"
            ),
            {"scope": scope, "key": key, "wid": workspace_id},
        )
    ).scalar_one_or_none()
    if role_id is None:
        raise LookupError(
            f"no is_system role for scope={scope!r} key={key!r} "
            f"workspace_id={workspace_id!r}"
        )
    await db.execute(
        text(
            "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
            "VALUES (:u, :r, :w, :g) "
            "ON CONFLICT (auth_user_id, role_id, workspace_id) DO NOTHING"
        ),
        {"u": auth_user_id, "r": role_id, "w": workspace_id, "g": granted_by},
    )
