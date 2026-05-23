"""Pydantic schemas for ``GET /api/workspaces/{wid}/members`` (list endpoint).

``email`` is nullable because the underlying LEFT JOIN to ``auth.users`` can
return NULL if a member's auth row was hard-deleted (the row in
``tenant_memberships`` survives via ON DELETE SET NULL — see migration 0001).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from ..models.tenant_membership import TenantRole


class WorkspaceMemberListItemOut(BaseModel):
    """One workspace member as seen by the workspace-members list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: EmailStr | None
    role: TenantRole
    joined_at: datetime
    granted_role_count: int


class WorkspaceMembersPage(BaseModel):
    items: list[WorkspaceMemberListItemOut]
    next_cursor: str | None = None
