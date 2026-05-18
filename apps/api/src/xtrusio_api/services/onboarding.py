"""Onboarding: create a tenant + owner membership atomically."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tenant import Tenant
from ..models.tenant_membership import TenantMembership, TenantRole
from ..rbac.grants import grant_role
from ..rbac.reconcile import reconcile_rbac
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
    # Seed this brand-new workspace's 4 system roles (migration 0006 only seeded
    # tenants existing at migrate time, so this tenant has no `roles` rows yet).
    # reconcile_rbac only wires role_permissions for EXISTING role rows, so the
    # role rows must be inserted first; reconcile_rbac then wires their perms.
    await db.execute(
        text(
            "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
            "SELECT 'workspace', :tid, v.key, v.key, '', true FROM (VALUES "
            "('owner'),('admin'),('editor'),('read_only')) AS v(key) "
            "ON CONFLICT DO NOTHING"
        ),
        {"tid": tenant.id},
    )
    await db.flush()
    # reconcile_rbac commits once at its end — this single commit atomically
    # persists the tenant, the OWNER membership, and the new role rows together
    # (tenant + membership stay inseparable). It is idempotent and re-wires
    # role_permissions for every workspace system role, including these new ones.
    await reconcile_rbac(db)
    # Now the 'owner' role row exists with its perms; grant it to the owner.
    await grant_role(
        db, auth_user_id=user_id, scope="workspace", key="owner",
        workspace_id=tenant.id,
    )
    await db.commit()
    await db.refresh(tenant)
    return tenant
