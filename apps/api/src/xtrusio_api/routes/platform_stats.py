"""GET /api/platform/stats — platform dashboard metrics.

Base reachability gate: ``platform.users.read`` (the platform dashboard's nav
perm) — 403 otherwise. Per-metric gates layer on top: each metric is included
only if the caller also holds its specific permission, otherwise the field is
``null`` and the frontend omits that card.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.permissions import has_permission, require_permission
from ..schemas.platform_stats import PlatformStats
from ..services.platform_stats import get_platform_stats

router = APIRouter(prefix="/api/platform", tags=["platform-stats"])

# Per-metric permission keys checked for inclusion in the response.
_METRIC_PERMS = (
    "platform.clients.read",
    "platform.users.read",
    "platform.audit.read",
)


@router.get("/stats", response_model=PlatformStats)
async def get_stats(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformStats:
    await require_permission(db, user.user_id, "platform.users.read")
    authorized = {key for key in _METRIC_PERMS if await has_permission(db, user.user_id, key)}
    return await get_platform_stats(db, authorized=authorized)
