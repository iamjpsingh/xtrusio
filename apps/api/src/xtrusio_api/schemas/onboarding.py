"""Request/response schemas for /api/onboarding/tenants."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from ..models.tenant_membership import TenantRole


class CreateTenantRequest(BaseModel):
    workspace_name: str = Field(min_length=2, max_length=200)


class CreatedTenant(BaseModel):
    id: UUID
    slug: str
    name: str
    role: TenantRole


class CreateTenantResponse(BaseModel):
    tenant: CreatedTenant
