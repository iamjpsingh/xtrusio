"""GET/POST/DELETE /api/workspaces/{wid}/members/{uid}/roles.

GET gated by `workspace.members.read`; POST and DELETE gated by
`workspace.members.manage`. The service layer owns the ≥1-owner floor +
priv-escalation pre-checks (DB trigger 0009 is defense-in-depth).
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.workspace_role import (
    WorkspaceRoleGrantIn,
    WorkspaceRoleGrantOut,
    WorkspaceRoleGrantsPage,
)
from ..services.workspace_role_grants import (
    GrantNotFoundError,
    MembershipNotFoundError,
    OwnerFloorError,
    PrivilegeEscalationError,
    RoleNotFoundError,
    RoleScopeMismatchError,
    grant_workspace_role,
    list_workspace_role_grants,
    revoke_workspace_role_grant,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["workspace-role-grants"])


@router.get(
    "/{workspace_id}/members/{user_id}/roles",
    response_model=WorkspaceRoleGrantsPage,
)
async def list_grants(
    workspace_id: UUID,
    user_id: UUID,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> WorkspaceRoleGrantsPage:
    await require_permission(db, user.user_id, "workspace.members.read", workspace_id=workspace_id)
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_workspace_role_grants(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        cursor=decoded,
        limit=params.effective_limit,
    )
    return WorkspaceRoleGrantsPage(
        items=[WorkspaceRoleGrantOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post(
    "/{workspace_id}/members/{user_id}/roles",
    response_model=WorkspaceRoleGrantOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_grant(
    workspace_id: UUID,
    user_id: UUID,
    body: WorkspaceRoleGrantIn,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRoleGrantOut:
    await require_permission(
        db, user.user_id, "workspace.members.manage", workspace_id=workspace_id
    )
    try:
        row = await grant_workspace_role(
            db,
            actor_id=user.user_id,
            workspace_id=workspace_id,
            target_user_id=user_id,
            role_id=body.role_id,
        )
        await db.commit()
    except MembershipNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "membership_not_found") from e
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
                "workspace_id": str(workspace_id),
                "missing_perm_key": e.missing_perm_key,
            },
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "privilege_escalation") from e
    return WorkspaceRoleGrantOut.model_validate(row)


@router.delete(
    "/{workspace_id}/members/{user_id}/roles/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_grant(
    workspace_id: UUID,
    user_id: UUID,
    grant_id: UUID,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await require_permission(
        db, user.user_id, "workspace.members.manage", workspace_id=workspace_id
    )
    try:
        await revoke_workspace_role_grant(
            db,
            actor_id=user.user_id,
            workspace_id=workspace_id,
            user_id=user_id,
            grant_id=grant_id,
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
                "workspace_id": str(workspace_id),
                "missing_perm_key": e.missing_perm_key,
            },
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "privilege_escalation") from e
    except OwnerFloorError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "owner_floor") from e
    except IntegrityError as e:
        # H10: the service-side count pre-check has a TOCTOU window; the 0010
        # ``trg_user_roles_owner_floor`` trigger is the real serialiser. When
        # the slower of two concurrent owner-revokes loses the FOR-UPDATE race,
        # the trigger raises ``last_owner`` (check_violation) on DELETE. Map it
        # to the same 409 the service-side OwnerFloorError uses.
        await db.rollback()
        if "last_owner" in str(e.orig):
            raise HTTPException(status.HTTP_409_CONFLICT, "owner_floor") from e
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
