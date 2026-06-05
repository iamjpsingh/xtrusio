"""Platform client-detail service.

Backs ``GET /api/platform/clients/{slug}``. Loads ONE client tenant by slug plus
its members, for a PLATFORM-scope caller (``platform.clients.read``) who is NOT
necessarily a member of the tenant — so it deliberately does NOT filter by the
caller's membership. Cross-tenant visibility is the intended capability here; the
route is the authorization gate.

LEFT JOIN to ``auth.users`` mirrors ``list_workspace_members``: a member's auth
row could be hard-deleted while its ``tenant_memberships`` row survives, so the
service surfaces ``email = None`` rather than dropping the member.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_client_by_slug(db: AsyncSession, *, slug: str) -> dict[str, Any] | None:
    """Return the tenant row (id, slug, name, created_at) for ``slug``.

    ``None`` if no tenant has that slug — the route maps this to a sanitized 404.
    """
    row = (
        (
            await db.execute(
                text(
                    "SELECT id, slug, name, created_at " "FROM tenants WHERE slug = :slug LIMIT 1"
                ),
                {"slug": slug},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def list_client_members(db: AsyncSession, *, tenant_id: UUID) -> list[dict[str, Any]]:
    """All members of ``tenant_id`` with email + role + joined_at.

    Ordered ``created_at ASC, id ASC`` (oldest-joined first — the owner that
    provisioned the tenant tends to sort first). Inline (uncapped) list: see the
    schema docstring for the bounded-membership rationale.
    """
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT tm.user_id AS auth_user_id, au.email, tm.role,
                       tm.created_at AS joined_at
                FROM tenant_memberships tm
                LEFT JOIN auth.users au ON au.id = tm.user_id
                WHERE tm.tenant_id = :tid
                ORDER BY tm.created_at ASC, tm.id ASC
                """
                ),
                {"tid": str(tenant_id)},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]
