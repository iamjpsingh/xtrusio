"""Pydantic schemas for invite endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from ..models.platform_user import PlatformRole
from ..models.tenant_membership import TenantRole

# Platform invites -----------------------------------------------------------


class CreatePlatformInviteRequest(BaseModel):
    email: EmailStr
    role: PlatformRole  # CHECK constraint in DB rejects 'super_admin'


class PlatformInviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: PlatformRole
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class PlatformInvitesPage(BaseModel):
    items: list[PlatformInviteResponse]
    next_cursor: str | None = None


# Tenant invites -------------------------------------------------------------


class CreateTenantInviteRequest(BaseModel):
    email: EmailStr
    role: TenantRole  # CHECK rejects 'owner'


class TenantInviteResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: EmailStr
    role: TenantRole
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class TenantInvitesPage(BaseModel):
    items: list[TenantInviteResponse]
    next_cursor: str | None = None


# Acceptance ----------------------------------------------------------------


class AcceptInviteResult(BaseModel):
    kind: Literal["platform", "tenant"]
    role: str
    tenant_id: UUID | None = None
