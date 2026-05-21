"""Pydantic schemas for workspace-role endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceRoleIn(BaseModel):
    """Create-payload for a custom workspace role."""

    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permission_keys: list[str] = Field(default_factory=list)


class WorkspaceRolePatch(BaseModel):
    """Partial-update payload. None means 'leave unchanged'."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permission_keys: list[str] | None = None


class WorkspaceRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    key: str
    name: str
    description: str | None
    is_system: bool
    permission_keys: list[str]
    created_at: datetime
    updated_at: datetime


class WorkspaceRolesPage(BaseModel):
    items: list[WorkspaceRoleOut]
    next_cursor: str | None = None


class WorkspaceRoleGrantIn(BaseModel):
    """Create-payload for `POST /api/workspaces/{wid}/members/{uid}/roles`."""

    role_id: UUID


class WorkspaceRoleGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    auth_user_id: UUID
    workspace_id: UUID
    role_id: UUID
    role_key: str
    granted_at: datetime
    granted_by: UUID | None


class WorkspaceRoleGrantsPage(BaseModel):
    items: list[WorkspaceRoleGrantOut]
    next_cursor: str | None = None
