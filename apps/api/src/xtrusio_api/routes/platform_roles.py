"""GET/POST/PATCH/DELETE /api/platform/roles — super_admin only.

All endpoints gated by `platform.roles.manage` (which super_admin holds and the
seeded `admin` platform role does NOT — see catalog.SYSTEM_ROLE_PERMISSIONS).
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.platform_role import (
    PlatformRoleIn,
    PlatformRoleOut,
    PlatformRolePatch,
    PlatformRolesPage,
)
from ..services.platform_roles import (
    PrivilegeEscalationError,
    RoleKeyTakenError,
    RoleNotFoundError,
    ScopeMismatchError,
    SystemRoleImmutableError,
    UnknownPermissionError,
    create_platform_role,
    delete_platform_role,
    get_platform_role,
    list_platform_roles,
    update_platform_role,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/roles", tags=["platform-roles"])


@router.get("", response_model=PlatformRolesPage)
async def list_roles(
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PlatformRolesPage:
    await require_permission(db, user.user_id, "platform.roles.manage")
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_platform_roles(db, cursor=decoded, limit=params.effective_limit)
    return PlatformRolesPage(
        items=[PlatformRoleOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post("", response_model=PlatformRoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: PlatformRoleIn,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformRoleOut:
    await require_permission(db, user.user_id, "platform.roles.manage")
    try:
        row = await create_platform_role(
            db,
            actor_id=user.user_id,
            key=body.key,
            name=body.name,
            description=body.description,
            permission_keys=body.permission_keys,
        )
        await db.commit()
    except RoleKeyTakenError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "role_key_taken") from e
    except UnknownPermissionError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except ScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except PrivilegeEscalationError as e:
        await db.rollback()
        # PAR-A M22: sanitize — the missing perm key would leak the RBAC graph.
        # Keep it server-side only (WARN log); return the bare constant.
        _log.warning(
            "privilege_escalation",
            extra={"actor_id": str(user.user_id), "missing_perm_key": e.missing_perm_key},
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "privilege_escalation") from e
    return PlatformRoleOut.model_validate(row)


@router.get("/{role_id}", response_model=PlatformRoleOut)
async def get_role(
    role_id: UUID,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformRoleOut:
    await require_permission(db, user.user_id, "platform.roles.manage")
    try:
        row = await get_platform_role(db, role_id=role_id)
    except RoleNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    return PlatformRoleOut.model_validate(row)


@router.patch("/{role_id}", response_model=PlatformRoleOut)
async def update_role(
    role_id: UUID,
    body: PlatformRolePatch,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformRoleOut:
    await require_permission(db, user.user_id, "platform.roles.manage")
    try:
        row = await update_platform_role(
            db,
            actor_id=user.user_id,
            role_id=role_id,
            name=body.name,
            description=body.description,
            permission_keys=body.permission_keys,
        )
        await db.commit()
    except RoleNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    except SystemRoleImmutableError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "system_role_immutable") from e
    except UnknownPermissionError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except ScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except PrivilegeEscalationError as e:
        await db.rollback()
        # PAR-A M22: sanitize — the missing perm key would leak the RBAC graph.
        _log.warning(
            "privilege_escalation",
            extra={"actor_id": str(user.user_id), "missing_perm_key": e.missing_perm_key},
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "privilege_escalation") from e
    return PlatformRoleOut.model_validate(row)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_role(
    role_id: UUID,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await require_permission(db, user.user_id, "platform.roles.manage")
    try:
        await delete_platform_role(db, actor_id=user.user_id, role_id=role_id)
        await db.commit()
    except RoleNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    except SystemRoleImmutableError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "system_role_immutable") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
