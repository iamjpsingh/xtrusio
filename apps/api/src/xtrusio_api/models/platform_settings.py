"""Platform-wide settings singleton (id always = 1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, DateTime, SmallInteger, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    signups_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PlatformSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signups_enabled: bool
    updated_at: datetime
    updated_by_email: str | None = None
