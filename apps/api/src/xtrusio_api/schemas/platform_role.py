"""Pydantic schemas for platform-role endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlatformRoleIn(BaseModel):
    """Create-payload for a custom platform role."""

    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permission_keys: list[str] = Field(default_factory=list)


class PlatformRolePatch(BaseModel):
    """Partial-update payload. None means 'leave unchanged'."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permission_keys: list[str] | None = None


class PlatformRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    name: str
    description: str | None
    is_system: bool
    permission_keys: list[str]
    created_at: datetime
    updated_at: datetime


class PlatformRolesPage(BaseModel):
    items: list[PlatformRoleOut]
    next_cursor: str | None = None


class PlatformRoleGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    auth_user_id: UUID
    role_id: UUID
    role_key: str
    granted_at: datetime
    granted_by: UUID | None


class PlatformRoleGrantsPage(BaseModel):
    items: list[PlatformRoleGrantOut]
    next_cursor: str | None = None
