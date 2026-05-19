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


async def create_tenant_with_owner(
    db: AsyncSession, *, user_id: UUID, workspace_name: str
) -> Tenant:
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
    await db.commit()
    await db.refresh(tenant)
    return tenant
