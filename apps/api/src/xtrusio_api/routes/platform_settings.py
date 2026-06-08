"""GET/PUT /api/platform/settings — super_admin only writes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..core.permissions import require_permission
from ..schemas.platform_settings import (
    PlatformSettingsResponse,
    UpdatePlatformSettingsRequest,
)
from ..services.platform_settings import get_platform_settings, update_settings

router = APIRouter(prefix="/api/platform/settings", tags=["platform-settings"])


@router.get("", response_model=PlatformSettingsResponse)
async def read(
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformSettingsResponse:
    await require_permission(db, user.user_id, "platform.settings.read")
    row, email = await get_platform_settings(db)
    return PlatformSettingsResponse(
        signups_enabled=row.signups_enabled,
        updated_at=row.updated_at,
        updated_by_email=email,
    )


@router.put("", response_model=PlatformSettingsResponse)
async def update(
    body: UpdatePlatformSettingsRequest,
    user: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformSettingsResponse:
    await require_permission(db, user.user_id, "platform.settings.manage")
    row, email = await update_settings(
        db, signups_enabled=body.signups_enabled, updated_by=user.user_id
    )
    # PAR-D M1: build the response from live (pre-commit) values, then commit.
    response = PlatformSettingsResponse(
        signups_enabled=row.signups_enabled,
        updated_at=row.updated_at,
        updated_by_email=email,
    )
    await db.commit()
    return response
