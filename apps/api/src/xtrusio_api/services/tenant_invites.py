"""Tenant invites: create / list / revoke."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import write_audit_event
from ..core.permissions import require_permission
from ..models.tenant_invite import TenantInvite
from ..models.tenant_membership import TenantMembership, TenantRole
from .invite_outbox import enqueue_invite_email
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

    # PAR-D H5/M1: stage the invite email in the outbox (same tx as the invite
    # row); the route commits and the worker sends it out of band. No
    # supabase_user_id writeback — tenant invites don't track it (the invited
    # email may belong to an already-existing Supabase user).
    # PAR-A C2: app_metadata (service-role-only writable) carries the invite id.
    await enqueue_invite_email(
        db,
        email=email,
        app_metadata={
            "tenant_invite_id": str(invite_id),
            "tenant_id": str(tenant_id),
            "tenant_role": role.value,
        },
    )
    # Audit coverage (same tx — route owns the commit).
    await write_audit_event(
        db,
        actor_id=inviter_id,
        action="tenant_invite.create",
        target_type="invite",
        target_id=invite_id,
        scope="workspace",
        workspace_id=tenant_id,
        after={"email": email, "role": role.value},
    )
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
    # PAR-D L4: lock the invite row so two concurrent revokes serialise — the
    # loser re-reads ``revoked_at`` set and no-ops idempotently instead of both
    # racing past the early-return.
    invite = (
        await db.execute(
            select(TenantInvite)
            .where(and_(TenantInvite.id == invite_id, TenantInvite.tenant_id == tenant_id))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if invite is None:
        return  # idempotent: revoking an unknown invite is a 204 no-op
    if invite.accepted_at is not None:
        raise InviteAlreadyAcceptedError()
    if invite.revoked_at is not None:
        return  # already revoked — idempotent no-op
    # Capture the before-payload from the loaded row BEFORE mutating it.
    before = {"email": invite.email, "role": invite.role.value}
    invite.revoked_at = datetime.now(UTC)
    # Audit row in the SAME tx as the revoke — this fn self-commits, so the
    # event MUST be written before the commit below.
    await write_audit_event(
        db,
        actor_id=requester_id,
        action="tenant_invite.revoke",
        target_type="invite",
        target_id=invite_id,
        scope="workspace",
        workspace_id=tenant_id,
        before=before,
    )
    await db.commit()
    # NOTE: unlike revoke_platform_invite, we intentionally do NOT delete the
    # Supabase auth.users row here. A tenant invite's email may belong to a
    # user who is a legitimate member of other tenants; deleting their auth
    # identity on one tenant's revoke would be a cross-tenant destructive
    # action. Auth-user lifecycle is not tied to a single tenant invite.
