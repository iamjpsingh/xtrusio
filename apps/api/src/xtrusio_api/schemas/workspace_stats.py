"""Pydantic schema for ``GET /api/workspaces/{workspace_id}/stats``.

A plain ``BaseModel``: the service assembles a dict of counts, there's no ORM
row to map. Every field is ``int | None`` — ``None`` means the caller lacks
the metric's permission, so the query never ran and the frontend omits the
card.
"""

from __future__ import annotations

from pydantic import BaseModel


class WorkspaceStats(BaseModel):
    """Per-metric workspace dashboard counts. ``None`` = not authorized."""

    members: int | None = None
    pending_invites: int | None = None
    recent_activity: int | None = None
