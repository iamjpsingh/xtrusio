"""Pydantic schema for ``GET /api/platform/stats`` (dashboard metrics).

A plain ``BaseModel`` (not ``from_attributes`` — there's no ORM row to map
from; the service assembles a dict of counts). Every field is ``int | None``:
``None`` means the caller is NOT authorized for that metric, so the service
never even ran its ``count(*)`` and the frontend omits that card entirely.
"""

from __future__ import annotations

from pydantic import BaseModel


class PlatformStats(BaseModel):
    """Per-metric platform dashboard counts. ``None`` = not authorized."""

    client_tenants: int | None = None
    active_platform_users: int | None = None
    recent_activity: int | None = None
