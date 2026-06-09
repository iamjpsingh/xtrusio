"""GET /api/permissions/catalog — read-only, non-secret.

The catalog is identical for every logged-in caller. No permission gate
because the data is non-secret (it's already visible in any 403 error
message), and gating it would just make the frontend permission picker
brittle for low-privilege users it shouldn't be brittle for.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..core.auth import AuthIdentity, require_authenticated
from ..rbac.catalog import CATALOG
from ..schemas.permission import PermissionDef, PermissionsCatalog

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


@router.get("/catalog", response_model=PermissionsCatalog)
async def get_catalog(
    _user: Annotated[AuthIdentity, Depends(require_authenticated)],
) -> PermissionsCatalog:
    return PermissionsCatalog(
        items=[
            PermissionDef(
                scope=p.scope,
                key=p.key,
                category=p.category,
                description=p.description,
            )
            for p in CATALOG
        ]
    )
