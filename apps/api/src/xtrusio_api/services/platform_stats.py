"""Platform dashboard stats service.

Backs ``GET /api/platform/stats``. Computes ONE ``count(*)`` per metric the
caller is authorized for and skips the query entirely for metrics they can't
read (don't-compute-then-hide — the unauthorized metric is never queried, so
the count never leaves the DB).

Read-only, caller-owns-tx (no commit). The route resolves the authorized set
via ``has_permission`` and passes it here; this module only decides which
``count(*)`` to run from that set, then runs it.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.platform_stats import PlatformStats


async def _count(db: AsyncSession, sql: str) -> int:
    """Run a parameterless ``SELECT count(*)`` and return the scalar."""
    return int((await db.execute(text(sql))).scalar_one())


async def get_platform_stats(db: AsyncSession, *, authorized: set[str]) -> PlatformStats:
    """Assemble the platform dashboard metrics for an authorized perm set.

    ``authorized`` is the subset of per-metric permission keys the caller
    holds. A metric whose key is absent stays ``None`` (the frontend omits its
    card). The 7-day activity window is fixed.
    """
    client_tenants: int | None = None
    active_platform_users: int | None = None
    recent_activity: int | None = None

    if "platform.clients.read" in authorized:
        client_tenants = await _count(db, "SELECT count(*) FROM tenants")
    if "platform.users.read" in authorized:
        active_platform_users = await _count(
            db, "SELECT count(*) FROM platform_users WHERE is_active"
        )
    if "platform.audit.read" in authorized:
        recent_activity = await _count(
            db,
            "SELECT count(*) FROM rbac_audit_log "
            "WHERE scope = 'platform' "
            "AND created_at > now() - interval '7 days'",
        )

    return PlatformStats(
        client_tenants=client_tenants,
        active_platform_users=active_platform_users,
        recent_activity=recent_activity,
    )
