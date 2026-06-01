"""Request/response schemas for ``POST /api/platform/users`` (direct-create).

A platform user with ``platform.users.manage`` can provision another platform
user directly (id + password) without an invite round-trip. The role is pinned
to ``admin`` only: ``super_admin`` stays CLI/seed-pinned (the 0010
single-super_admin invariant), and the legacy ``editor`` platform role has no
RBAC system role so cannot be granted on creation.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class PlatformUserCreate(BaseModel):
    """Direct-create request: email + password + role (``admin`` only)."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin"]


class PlatformUserCreated(BaseModel):
    """The newly provisioned platform user."""

    id: UUID
    email: EmailStr
    role: Literal["admin"]
    is_active: bool
