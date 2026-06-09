"""Pydantic schemas for ``GET/PUT /api/workspaces/{wid}/settings``.

``WorkspaceSettingsOut`` is a thin projection of the ``tenants`` row tailored
to the settings page (no ``created_by`` exposed; slug shown read-only).
``WorkspaceSettingsUpdate`` is the MVP edit body — only ``name`` is mutable
in P6d; slug rename / description / timezone are deliberately deferred (see
the P6d plan section 1 out-of-scope list).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceSettingsOut(BaseModel):
    """Read projection of a tenant row for the settings page."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    created_at: datetime
    updated_at: datetime


class WorkspaceSettingsUpdate(BaseModel):
    """PUT body — only ``name`` may be changed in P6d."""

    name: str = Field(min_length=1, max_length=200)
