"""GET/POST/DELETE /api/platform/users/{user_id}/roles — platform-role grants.

GET is gated by ``platform.users.read``; POST and DELETE by ``platform.users.manage``.
The single-super_admin invariant and the priv-escalation guard live in the
service layer (and are also defense-in-depth-enforced by the 0009 DB trigger).
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.platform_role import (
    PlatformRoleGrantIn,
    PlatformRoleGrantOut,
    PlatformRoleGrantsPage,
)
from ..services.platform_role_grants import (
    GrantNotFoundError,
    PlatformUserNotFoundError,
    PrivilegeEscalationError,
    RoleNotFoundError,
    RoleScopeMismatchError,
    SingleSuperAdminError,
    grant_platform_role,
    list_platform_role_grants,
    revoke_platform_role_grant,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/users", tags=["platform-role-grants"])


@router.get("/{user_id}/roles", response_model=PlatformRoleGrantsPage)
async def list_grants(
    user_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PlatformRoleGrantsPage:
    await require_permission(db, user.user_id, "platform.users.read")
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_platform_role_grants(
        db, user_id=user_id, cursor=decoded, limit=params.effective_limit
    )
    return PlatformRoleGrantsPage(
        items=[PlatformRoleGrantOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post(
    "/{user_id}/roles",
    response_model=PlatformRoleGrantOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_grant(
    user_id: UUID,
    body: PlatformRoleGrantIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformRoleGrantOut:
    await require_permission(db, user.user_id, "platform.users.manage")
    try:
        row = await grant_platform_role(
            db, actor_id=user.user_id, target_user_id=user_id, role_id=body.role_id
        )
        await db.commit()
    except PlatformUserNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "platform_user_not_found") from e
    except RoleNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    except RoleScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "role_scope_mismatch") from e
    except PrivilegeEscalationError as e:
        await db.rollback()
        # PAR-A M22: sanitize the response body — the missing perm key is a
        # leak of the internal RBAC graph (lets an attacker enumerate what
        # they'd need to escalate). Keep the perm key on the exception for
        # server-side logging only.
        _log.warning(
            "privilege_escalation",
            extra={
                "actor_id": str(user.user_id),
                "missing_perm_key": e.missing_perm_key,
            },
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "privilege_escalation") from e
    except SingleSuperAdminError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "single_super_admin_invariant") from e
    return PlatformRoleGrantOut.model_validate(row)


@router.delete(
    "/{user_id}/roles/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_grant(
    user_id: UUID,
    grant_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await require_permission(db, user.user_id, "platform.users.manage")
    try:
        await revoke_platform_role_grant(
            db, actor_id=user.user_id, user_id=user_id, grant_id=grant_id
        )
        await db.commit()
    except GrantNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "grant_not_found") from e
    except RoleScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "role_scope_mismatch") from e
    except PrivilegeEscalationError as e:
        await db.rollback()
        # PAR-A M22: sanitize the response body — the missing perm key is a
        # leak of the internal RBAC graph (lets an attacker enumerate what
        # they'd need to escalate). Keep the perm key on the exception for
        # server-side logging only.
        _log.warning(
            "privilege_escalation",
            extra={
                "actor_id": str(user.user_id),
                "missing_perm_key": e.missing_perm_key,
            },
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "privilege_escalation") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
