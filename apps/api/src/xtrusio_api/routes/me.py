"""GET /api/me — returns enriched current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..models.platform_user import PlatformUser, PlatformUserOut

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=PlatformUserOut)
async def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformUser:
    row = (
        await db.execute(select(PlatformUser).where(PlatformUser.id == user.user_id))
    ).scalar_one()
    return row
