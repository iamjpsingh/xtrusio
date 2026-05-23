"""Idempotent user_roles grant helper — the single write path for granting a
role to a principal. Resolves the roles row by (scope, key[, workspace_id])
and inserts user_roles using a pre-SELECT then INSERT pattern. Used by
onboarding, invite-acceptance, bootstrap, and the enum→user_roles reconciler.

Why pre-SELECT instead of ON CONFLICT DO NOTHING: Postgres' default
NULLS DISTINCT semantics treat each NULL as distinct, so the UNIQUE
constraint on (auth_user_id, role_id, workspace_id) does NOT match two
platform grants with workspace_id IS NULL — meaning ON CONFLICT can't
catch the duplicate and we'd end up with two rows. The pre-SELECT uses
``IS NOT DISTINCT FROM`` so NULL == NULL, catching the duplicate in both
the platform (NULL) and workspace (NOT NULL) cases.

Concurrent identical grants still race in a small TOCTOU window between
the SELECT and the INSERT — one wins, the loser raises IntegrityError.
That's acceptable for every existing caller (onboarding, invite-acceptance,
bootstrap are once-per-user; the reconciler is single-process at startup
and via `make rbac-seed`).
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
            f"no is_system role for scope={scope!r} key={key!r} " f"workspace_id={workspace_id!r}"
        )
    existing = (
        await db.execute(
            text(
                "SELECT 1 FROM user_roles "
                "WHERE auth_user_id = :u AND role_id = :r "
                "AND workspace_id IS NOT DISTINCT FROM :w"
            ),
            {"u": auth_user_id, "r": role_id, "w": workspace_id},
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    await db.execute(
        text(
            "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
            "VALUES (:u, :r, :w, :g)"
        ),
        {"u": auth_user_id, "r": role_id, "w": workspace_id, "g": granted_by},
    )
