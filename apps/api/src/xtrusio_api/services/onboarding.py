"""Onboarding: create a tenant + owner membership atomically."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tenant import Tenant
from ..models.tenant_membership import TenantMembership, TenantRole
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
    await db.commit()
    await db.refresh(tenant)
    return tenant
