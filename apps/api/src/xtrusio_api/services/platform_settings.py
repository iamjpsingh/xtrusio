"""Read/write platform_settings."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.platform_settings import PlatformSettings
from ..models.platform_user import PlatformUser


async def get_settings(db: AsyncSession) -> tuple[PlatformSettings, str | None]:
    row = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))).scalar_one()
    updated_by_email: str | None = None
    if row.updated_by is not None:
        updater = (
            await db.execute(select(PlatformUser).where(PlatformUser.id == row.updated_by))
        ).scalar_one_or_none()
        updated_by_email = updater.email if updater else None
    return row, updated_by_email


async def is_signups_enabled(db: AsyncSession) -> bool:
    row = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))).scalar_one()
    return row.signups_enabled


async def update_settings(
    db: AsyncSession, *, signups_enabled: bool, updated_by: UUID
) -> tuple[PlatformSettings, str | None]:
    row = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))).scalar_one()
    row.signups_enabled = signups_enabled
    row.updated_by = updated_by
    await db.commit()
    await db.refresh(row)
    return await get_settings(db)
