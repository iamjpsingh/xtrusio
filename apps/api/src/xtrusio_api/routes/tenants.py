"""GET/POST /api/tenants."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CursorParams,
    encode_cursor,
)
from ..core.permissions import require_permission
from ..models.tenant import Tenant, TenantIn, TenantOut, TenantsPage

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


@router.get("", response_model=TenantsPage)
async def list_tenants(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> TenantsPage:
    await require_permission(db, user.user_id, "platform.clients.read")
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e

    stmt = select(Tenant).order_by(Tenant.created_at.desc(), Tenant.id.desc())
    if decoded is not None:
        ts, rid = decoded
        stmt = stmt.where(tuple_(Tenant.created_at, Tenant.id) < (ts, rid))
    stmt = stmt.limit(params.effective_limit + 1)

    rows = list((await db.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > params.effective_limit:
        last = rows[params.effective_limit - 1]
        next_cursor = encode_cursor(last.created_at, last.id)
        rows = rows[: params.effective_limit]
    return TenantsPage(items=[TenantOut.model_validate(t) for t in rows], next_cursor=next_cursor)


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Tenant:
    await require_permission(db, user.user_id, "platform.clients.manage")
    tenant = Tenant(slug=body.slug, name=body.name, created_by=user.user_id)
    db.add(tenant)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "slug already taken") from e
    await db.refresh(tenant)
    return tenant
