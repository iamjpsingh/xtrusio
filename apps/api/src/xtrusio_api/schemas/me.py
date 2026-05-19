"""Response schema for GET /api/me."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

from ..models.platform_user import PlatformRole
from ..models.tenant_membership import TenantRole


class PlatformContext(BaseModel):
    role: PlatformRole
    is_active: bool


class TenantContext(BaseModel):
    id: UUID
    slug: str
    name: str
    role: TenantRole
    # Resolver-derived effective workspace permission keys for this tenant.
    # Additive: `role` is kept until the frontend migrates (P6b).
    permissions: list[str]


class PendingInvite(BaseModel):
    kind: Literal["platform", "tenant"]
    id: UUID
    tenant_id: UUID | None
    role: str  # widened union of platform_role and tenant_role; validated server-side


class MeResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    platform: PlatformContext | None
    # Resolver-derived effective platform permission keys (empty if none).
    # Additive: `platform.role` is kept until the frontend migrates (P6b).
    platform_permissions: list[str]
    tenants: list[TenantContext]
    pending_invite: PendingInvite | None
