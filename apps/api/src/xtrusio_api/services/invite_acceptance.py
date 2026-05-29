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


def _is_provisioning_conflict(e: IntegrityError, *constraint_names: str) -> bool:
    """PAR-D M2: only treat an IntegrityError as 'already provisioned' when it
    is one of the EXPECTED uniqueness conflicts (the principal already exists).

    Mapping every IntegrityError to AlreadyProvisionedError lied about
    unrelated constraint violations (e.g. the workspace single-owner index) —
    masking real bugs as a benign 409. Inspect ``constraint_name`` (asyncpg
    surfaces it on ``e.orig``) and re-raise anything unexpected.
    """
    constraint = getattr(e.orig, "constraint_name", None) or str(e.orig)
    return any(name in constraint for name in constraint_names)


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
    # PAR-D M1: caller-owns-transaction — flush (not commit) so a uniqueness
    # conflict still surfaces as AlreadyProvisioned here; the route commits on
    # success and rolls back on any raised error.
    try:
        await db.flush()
    except IntegrityError as e:
        if _is_provisioning_conflict(e, "platform_users_pkey", "platform_users_email_key"):
            raise AlreadyProvisionedError() from e
        raise
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
    # PAR-D M1: flush (not commit); the route owns commit/rollback.
    try:
        await db.flush()
    except IntegrityError as e:
        if _is_provisioning_conflict(
            e, "tenant_memberships_tenant_id_user_id_key", "tenant_memberships_pkey"
        ):
            raise AlreadyProvisionedError() from e
        raise
    return {
        "kind": "tenant",
        "role": invite.role.value,
        "tenant_id": str(invite.tenant_id),
    }


async def accept_invite(
    db: AsyncSession, *, user_id: UUID, email: str, app_metadata: dict[str, Any]
) -> dict[str, Any]:
    """Read invite ids from ``app_metadata`` (PAR-A C2).

    The token's ``user_metadata`` claim is writable by the user's own access
    token (PUT /auth/v1/user) — accepting an invite id from there meant any
    confirmed user could forge ``platform_invite_id`` / ``tenant_invite_id``
    on themselves and self-promote. ``app_metadata`` is service-role-only
    writable, so the invitee cannot forge it.
    """
    platform_invite_id = app_metadata.get("platform_invite_id")
    tenant_invite_id = app_metadata.get("tenant_invite_id")
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
