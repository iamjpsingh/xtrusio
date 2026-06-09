"""GET /api/audit/catalog — read-only, non-secret event catalog.

The catalog (action -> label + category) is identical for every logged-in
caller. No permission gate because the data is non-secret metadata that drives
the activity-feed filter dropdown + the human-readable action labels; gating it
would just make the frontend brittle for low-privilege users it shouldn't be
brittle for. Mirrors `routes/permissions.py`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..core.audit_catalog import actions, categories
from ..core.auth import AuthIdentity, require_authenticated
from ..schemas.audit_catalog import AuditActionDef, AuditCatalog, AuditCategoryDef

router = APIRouter(prefix="/api/audit", tags=["audit-catalog"])


@router.get("/catalog", response_model=AuditCatalog)
async def get_catalog(
    _user: Annotated[AuthIdentity, Depends(require_authenticated)],
) -> AuditCatalog:
    return AuditCatalog(
        categories=[AuditCategoryDef(key=key, label=label) for key, label in categories()],
        actions=[
            AuditActionDef(action=action, label=label, category=cat)
            for action, label, cat in actions()
        ],
    )
