"""Pydantic schemas for the permissions catalog endpoint.

Mirrors `apps/api/src/xtrusio_api/rbac/catalog.py:CATALOG` 1:1. Read-only,
non-secret — exposed to any logged-in caller.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PermissionDef(BaseModel):
    scope: Literal["platform", "workspace"]
    key: str
    category: str
    description: str


class PermissionsCatalog(BaseModel):
    items: list[PermissionDef]
