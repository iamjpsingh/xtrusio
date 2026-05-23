"""Pydantic schemas for ``GET /api/platform/users`` (list endpoint).

Distinct from ``models/platform_user.py:PlatformUserOut`` because the list
endpoint joins to ``user_roles`` for a per-user grant count that the bare
``platform_users`` projection doesn't carry. The single-user grant projection
is served by ``GET /api/platform/users/{user_id}/roles`` (P4).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from ..models.platform_user import PlatformRole


class PlatformUserListItemOut(BaseModel):
    """One platform user as seen by the platform-users list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: PlatformRole
    is_active: bool
    created_at: datetime
    last_sign_in_at: datetime | None
    granted_role_count: int


class PlatformUsersPage(BaseModel):
    items: list[PlatformUserListItemOut]
    next_cursor: str | None = None
