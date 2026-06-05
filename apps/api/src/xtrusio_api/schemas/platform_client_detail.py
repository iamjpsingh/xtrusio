"""Pydantic schemas for ``GET /api/platform/clients/{slug}`` (client detail).

Platform-scope view of ONE client tenant + its members, for a platform operator
who provisioned (or otherwise has ``platform.clients.read``) but is NOT a member
of the tenant. Members are returned as an INLINE list (not paginated): a client
tenant is expected to hold a small, bounded number of members (a handful of
admins/editors), so a single round-trip is simpler than a cursor envelope and
keeps the page's "info + members" render in one fetch. If a client ever grows to
hundreds of members this should move to the cursor-paginated workspace-members
shape; the inline list is the deliberate first-cut tradeoff.

``email`` is nullable because the underlying LEFT JOIN to ``auth.users`` can
return NULL if a member's auth row was hard-deleted (the membership row survives
— mirrors ``WorkspaceMemberListItemOut``).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from ..models.tenant_membership import TenantRole


class PlatformClientMember(BaseModel):
    """One member of a client tenant as seen by the platform client-detail view."""

    model_config = ConfigDict(from_attributes=True)

    auth_user_id: UUID
    email: EmailStr | None
    role: TenantRole
    joined_at: datetime


class PlatformClientDetail(BaseModel):
    """A client tenant's info + members for a platform operator.

    ``owner_email`` is the email of the tenant's ``owner`` member (the first
    membership row with ``role = 'owner'``), or ``None`` if no owner row exists
    (e.g. a tenant provisioned but never joined). ``member_count`` is the total
    number of ``tenant_memberships`` rows, independent of the inline ``members``
    list length (they match today since the list is uncapped, but the field is
    explicit so the frontend never has to derive it).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    created_at: datetime
    owner_email: EmailStr | None = None
    member_count: int
    members: list[PlatformClientMember]
