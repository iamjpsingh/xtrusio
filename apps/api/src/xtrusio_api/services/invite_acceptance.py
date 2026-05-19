"""Accept a platform or tenant invite based on JWT user_metadata claims."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.platform_invite import PlatformInvite
from ..models.platform_user import PlatformUser
from ..models.tenant_invite import TenantInvite
from ..models.tenant_membership import TenantMembership
from ..rbac.grants import grant_role


class NoInviteError(Exception):
    pass


class InviteRevokedError(Exception):
    pass


class InviteExpiredError(Exception):
    pass


class InviteAlreadyAcceptedError(Exception):
    pass


class EmailMismatchError(Exception):
    pass


class AlreadyProvisionedError(Exception):
    pass


async def _accept_platform(
    db: AsyncSession, *, user_id: UUID, email: str, invite_id: UUID
) -> dict[str, Any]:
    invite = (
        await db.execute(select(PlatformInvite).where(PlatformInvite.id == invite_id))
    ).scalar_one_or_none()
    if invite is None:
        raise NoInviteError()
    if invite.revoked_at is not None:
        raise InviteRevokedError()
    if invite.accepted_at is not None:
        raise InviteAlreadyAcceptedError()
    if invite.expires_at < datetime.now(UTC):
        raise InviteExpiredError()
    if invite.email.lower() != email.lower():
        raise EmailMismatchError()

    db.add(PlatformUser(id=user_id, email=email, role=invite.role, is_active=True))
    # Also write the mapped user_roles grant in the SAME transaction as the
    # enum row (before the single commit below) so IntegrityError ->
    # AlreadyProvisionedError still applies and a re-accept stays idempotent
    # (grant_role is ON CONFLICT DO NOTHING). Only 'admin' has a platform
    # system role; legacy 'editor' has none (spec §2.7) so is intentionally
    # skipped (no raise); 'super_admin' can't reach here (schema rejects it).
    if invite.role.value == "admin":
        await grant_role(db, auth_user_id=user_id, scope="platform", key="admin")
    invite.accepted_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise AlreadyProvisionedError() from e
    return {"kind": "platform", "role": invite.role.value, "tenant_id": None}


async def _accept_tenant(
    db: AsyncSession, *, user_id: UUID, email: str, invite_id: UUID
) -> dict[str, Any]:
    invite = (
        await db.execute(select(TenantInvite).where(TenantInvite.id == invite_id))
    ).scalar_one_or_none()
    if invite is None:
        raise NoInviteError()
    if invite.revoked_at is not None:
        raise InviteRevokedError()
    if invite.accepted_at is not None:
        raise InviteAlreadyAcceptedError()
    if invite.expires_at < datetime.now(UTC):
        raise InviteExpiredError()
    if invite.email.lower() != email.lower():
        raise EmailMismatchError()

    db.add(TenantMembership(tenant_id=invite.tenant_id, user_id=user_id, role=invite.role))
    # Also write the mapped workspace user_roles grant in the SAME transaction
    # as the membership row (before the single commit below) so IntegrityError
    # -> AlreadyProvisionedError still applies and a re-accept stays idempotent
    # (grant_role is ON CONFLICT DO NOTHING). That tenant's 4 workspace system
    # roles already exist (tenant pre-existed at 0006 or was onboarded).
    await grant_role(
        db,
        auth_user_id=user_id,
        scope="workspace",
        key=invite.role.value,
        workspace_id=invite.tenant_id,
    )
    invite.accepted_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise AlreadyProvisionedError() from e
    return {
        "kind": "tenant",
        "role": invite.role.value,
        "tenant_id": str(invite.tenant_id),
    }


async def accept_invite(
    db: AsyncSession, *, user_id: UUID, email: str, user_metadata: dict[str, Any]
) -> dict[str, Any]:
    platform_invite_id = user_metadata.get("platform_invite_id")
    tenant_invite_id = user_metadata.get("tenant_invite_id")
    if platform_invite_id:
        try:
            pid = UUID(str(platform_invite_id))
        except ValueError as e:
            raise NoInviteError() from e
        return await _accept_platform(db, user_id=user_id, email=email, invite_id=pid)
    if tenant_invite_id:
        try:
            tid = UUID(str(tenant_invite_id))
        except ValueError as e:
            raise NoInviteError() from e
        return await _accept_tenant(db, user_id=user_id, email=email, invite_id=tid)
    raise NoInviteError()
