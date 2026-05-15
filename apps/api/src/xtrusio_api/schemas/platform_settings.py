"""Request/response schemas for /api/platform/settings."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PlatformSettingsResponse(BaseModel):
    signups_enabled: bool
    updated_at: datetime
    updated_by_email: str | None


class UpdatePlatformSettingsRequest(BaseModel):
    signups_enabled: bool
