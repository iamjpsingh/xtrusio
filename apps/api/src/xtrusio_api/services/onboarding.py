"""Onboarding: create a tenant + owner membership atomically."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tenant import Tenant
from ..models.tenant_membership import TenantMembership, TenantRole
from ..rbac.grants import grant_role
from ..rbac.reconcile import wire_workspace_role_perms
from .slug import slugify, unique_slug_from_taken


class AlreadyHasMembershipError(Exception):
    pass


# Advisory-lock namespace for onboarding (the two-int form keeps it distinct
# from any other advisory lock, e.g. the reconcile lock). 0x4F4E = "ON".
_ONBOARD_LOCK_NS = 0x4F4E


async def create_tenant_with_owner(
    db: AsyncSession, *, user_id: UUID, workspace_name: str
) -> Tenant:
    # PAR-D M6: serialise concurrent onboards for the SAME user. Two parallel
    # POST /onboarding/tenants both passed the membership existence-check below
    # and each created a tenant. A transaction-scoped advisory lock keyed on the
    # user id makes the check-then-create atomic; it auto-releases at commit/
    # rollback. Keyed per-user, so different users never block each other.
    # ``user_id.int % 2**31`` fits a signed int4 (the two-int lock form).
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :k)"),
        {"ns": _ONBOARD_LOCK_NS, "k": user_id.int % (2**31)},
    )
    existing = (
        await db.execute(select(TenantMembership).where(TenantMembership.user_id == user_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise AlreadyHasMembershipError()

    base = slugify(workspace_name)
    taken = {
        row
        for row in (await db.execute(select(Tenant.slug).where(Tenant.slug.like(f"{base}%"))))
        .scalars()
        .all()
    }
    slug = unique_slug_from_taken(base, taken)

    tenant = Tenant(slug=slug, name=workspace_name, created_by=user_id)
    db.add(tenant)
    await db.flush()  # gets server-generated id

    db.add(TenantMembership(tenant_id=tenant.id, user_id=user_id, role=TenantRole.OWNER))
    await db.flush()
    # 0006 only seeded workspace system roles for tenants existing at migrate
    # time; a brand-new tenant has none. Seed its 4 system roles (0006-friendly
    # name/description), wire ONLY this workspace's role_permissions, grant the
    # owner — all in the SINGLE commit below (atomic: no partial-failure window,
    # no global all-tenants reconcile on the request path).
    await db.execute(
        text(
            "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
            "SELECT 'workspace', :tid, v.key, v.name, v.description, true FROM (VALUES "
            "('owner','Owner','Governs the workspace; manages roles'),"
            "('admin','Admin','Operates the workspace; cannot manage roles'),"
            "('editor','Editor','Content write access'),"
            "('read_only','Read Only','View-only access')"
            ") AS v(key, name, description) ON CONFLICT DO NOTHING"
        ),
        {"tid": tenant.id},
    )
    await db.flush()
    await wire_workspace_role_perms(db, workspace_id=tenant.id)
    await grant_role(
        db,
        auth_user_id=user_id,
        scope="workspace",
        key="owner",
        workspace_id=tenant.id,
    )
    # PAR-D M1: caller-owns-transaction — the route commits on success and rolls
    # back on a typed error. ``tenant`` is flushed (id populated) but not yet
    # committed; the route reads its attributes before committing.
    return tenant
