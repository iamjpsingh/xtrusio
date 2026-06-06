"""Pydantic schemas for the audit event catalog endpoint.

Mirrors `apps/api/src/xtrusio_api/core/audit_catalog.py` 1:1. Read-only,
non-secret metadata (label + category per action) — exposed to any logged-in
caller, mirroring the permissions catalog.
"""

from __future__ import annotations

from pydantic import BaseModel


class AuditCategoryDef(BaseModel):
    key: str
    label: str


class AuditActionDef(BaseModel):
    action: str
    label: str
    category: str


class AuditCatalog(BaseModel):
    categories: list[AuditCategoryDef]
    actions: list[AuditActionDef]
