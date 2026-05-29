"""Tenant invites: create / list / revoke."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from gotrue.errors import AuthApiError, AuthRetryableError
from sqlalchemy import and_, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from supabase import create_client

from ..core.config import get_settings
from ..core.permissions import require_permission
from ..models.tenant_invite import TenantInvite
from ..models.tenant_membership import TenantMembership, TenantRole
from .invite_rules import can_invite

_TTL_DAYS = 7


class NotAMemberError(Exception):
    pass


class ForbiddenRoleError(Exception):
    pass


class UserAlreadyMemberError(Exception):
    pass


class InvitePendingError(Exception):
    pass


class InviteAlreadyAcceptedError(Exception):
    pass


class EmailProviderUnavailableError(Exception):
    pass


async def _load_membership(db: AsyncSession, *, tenant_id: UUID, user_id: UUID) -> TenantMembership:
    """Load the requester's membership (needed by `can_invite`).

    Authorization is the resolver's job (`require_permission`), NOT the enum
    role on this row. We still require a membership to exist so the established
    `not_a_member` (403) route contract is preserved and `can_invite` has the
    inviter's role to evaluate its business rule.
    """
    membership = (
        await db.execute(
            select(TenantMembership).where(
                and_(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == user_id,
                )
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise NotAMemberError()
    return membership


async def create_tenant_invite(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    inviter_id: UUID,
    email: str,
    role: TenantRole,
) -> TenantInvite:
    membership = await _load_membership(db, tenant_id=tenant_id, user_id=inviter_id)
    await require_permission(db, inviter_id, "workspace.members.invite", workspace_id=tenant_id)

    if not can_invite(inviter=membership.role, target=role):
        raise ForbiddenRoleError()

    member_row = (
        await db.execute(
            text(
                """
                SELECT 1
                FROM tenant_memberships m
                JOIN auth.users u ON u.id = m.user_id
                WHERE m.tenant_id = :tid AND lower(u.email) = lower(:email)
                LIMIT 1
                """
            ),
            {"tid": str(tenant_id), "email": email},
        )
    ).first()
    if member_row is not None:
        raise UserAlreadyMemberError()

    pending = (
        await db.execute(
            select(TenantInvite).where(
                and_(
                    TenantInvite.tenant_id == tenant_id,
                    TenantInvite.email == email,
                    TenantInvite.accepted_at.is_(None),
                    TenantInvite.revoked_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise InvitePendingError()

    invite = TenantInvite(
        tenant_id=tenant_id,
        email=email,
        role=role,
        invited_by=inviter_id,
        expires_at=datetime.now(UTC) + timedelta(days=_TTL_DAYS),
    )
    db.add(invite)
    await db.flush()
    invite_id = invite.id

    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def _call() -> Any:
        return sb.auth.admin.invite_user_by_email(email)

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_call), timeout=cfg.supabase_timeout_sec)
    except TimeoutError as e:
        await db.rollback()
        raise EmailProviderUnavailableError() from e
    except (AuthApiError, AuthRetryableError, httpx.HTTPError) as e:
        await db.rollback()
        raise EmailProviderUnavailableError() from e

    # PAR-A C2: write invite claims to ``app_metadata`` (service-role only
    # writable; the invitee can't forge it from their own session).
    sb_user_id: str | None = getattr(getattr(result, "user", None), "id", None)
    if isinstance(sb_user_id, str):

        def _set_app_metadata() -> Any:
            return sb.auth.admin.update_user_by_id(
                sb_user_id,
                {
                    "app_metadata": {
                        "tenant_invite_id": str(invite_id),
                        "tenant_id": str(tenant_id),
                        "tenant_role": role.value,
                    }
                },
            )

        try:
            await asyncio.wait_for(
                asyncio.to_thread(_set_app_metadata), timeout=cfg.supabase_timeout_sec
            )
        except TimeoutError as e:
            await db.rollback()
            raise EmailProviderUnavailableError() from e
        except (AuthApiError, AuthRetryableError, httpx.HTTPError) as e:
            await db.rollback()
            raise EmailProviderUnavailableError() from e

    await db.commit()
    await db.refresh(invite)
    return invite


async def list_tenant_invites(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    requester_id: UUID,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[TenantInvite], str | None]:
    from ..core.pagination import encode_cursor

    await _load_membership(db, tenant_id=tenant_id, user_id=requester_id)
    await require_permission(db, requester_id, "workspace.members.manage", workspace_id=tenant_id)
    stmt = (
        select(TenantInvite)
        .where(TenantInvite.tenant_id == tenant_id)
        .order_by(TenantInvite.created_at.desc(), TenantInvite.id.desc())
    )
    if cursor is not None:
        ts, rid = cursor
        stmt = stmt.where(tuple_(TenantInvite.created_at, TenantInvite.id) < (ts, rid))
    stmt = stmt.limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last.created_at, last.id)
        rows = rows[:limit]
    return rows, next_cursor


async def revoke_tenant_invite(
    db: AsyncSession, *, tenant_id: UUID, invite_id: UUID, requester_id: UUID
) -> None:
    await _load_membership(db, tenant_id=tenant_id, user_id=requester_id)
    await require_permission(db, requester_id, "workspace.members.manage", workspace_id=tenant_id)
    invite = (
        await db.execute(
            select(TenantInvite).where(
                and_(TenantInvite.id == invite_id, TenantInvite.tenant_id == tenant_id)
            )
        )
    ).scalar_one_or_none()
    if invite is None:
        return  # idempotent: revoking an unknown invite is a 204 no-op
    if invite.accepted_at is not None:
        raise InviteAlreadyAcceptedError()
    if invite.revoked_at is not None:
        return  # already revoked — idempotent no-op
    invite.revoked_at = datetime.now(UTC)
    await db.commit()
    # NOTE: unlike revoke_platform_invite, we intentionally do NOT delete the
    # Supabase auth.users row here. A tenant invite's email may belong to a
    # user who is a legitimate member of other tenants; deleting their auth
    # identity on one tenant's revoke would be a cross-tenant destructive
    # action. Auth-user lifecycle is not tied to a single tenant invite.
