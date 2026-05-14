"""GET/PUT /api/platform/settings — super_admin only writes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user, require_super_admin
from ..core.db import get_db
from ..schemas.platform_settings import (
    PlatformSettingsResponse,
    UpdatePlatformSettingsRequest,
)
from ..services.platform_settings import get_settings, update_settings

router = APIRouter(prefix="/api/platform/settings", tags=["platform-settings"])


@router.get("", response_model=PlatformSettingsResponse)
async def read(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformSettingsResponse:
    row, email = await get_settings(db)
    return PlatformSettingsResponse(
        signups_enabled=row.signups_enabled,
        updated_at=row.updated_at,
        updated_by_email=email,
    )


@router.put("", response_model=PlatformSettingsResponse)
async def update(
    body: UpdatePlatformSettingsRequest,
    user: Annotated[CurrentUser, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformSettingsResponse:
    row, email = await update_settings(
        db, signups_enabled=body.signups_enabled, updated_by=user.user_id
    )
    return PlatformSettingsResponse(
        signups_enabled=row.signups_enabled,
        updated_at=row.updated_at,
        updated_by_email=email,
    )
