"""Platform invites: create / list / revoke."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from gotrue.errors import AuthApiError, AuthRetryableError
from sqlalchemy import and_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from supabase import create_client

from ..core.audit import write_audit_event
from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.platform_invite import PlatformInvite
from ..models.platform_user import PlatformRole, PlatformUser
from .invite_outbox import enqueue_invite_email

_TTL_DAYS = 7
_log = get_logger(__name__)


class UnsupportedInviteRoleError(Exception):
    """PAR-D L5: the requested platform invite role has no RBAC system role and
    cannot be granted on acceptance (the legacy 'editor' platform role). Surfaced
    as a 400 instead of silently provisioning a roleless platform user."""

    def __init__(self, role: str) -> None:
        super().__init__(f"unsupported platform invite role: {role}")
        self.role = role


class UserExistsError(Exception):
    pass


class InvitePendingError(Exception):
    pass


async def create_platform_invite(
    db: AsyncSession,
    *,
    email: str,
    role: PlatformRole,
    invited_by: UUID,
) -> PlatformInvite:
    # PAR-D L5: only 'admin' maps to a platform RBAC system role. 'editor' is a
    # legacy enum value with no system role (accepting it would create a
    # roleless platform_user — a silent dead path); 'super_admin' is
    # bootstrap-only and never invitable. Reject both up front.
    if role != PlatformRole.ADMIN:
        raise UnsupportedInviteRoleError(role.value)

    existing_pu = (
        await db.execute(select(PlatformUser).where(PlatformUser.email == email))
    ).scalar_one_or_none()
    if existing_pu is not None:
        raise UserExistsError()

    pending = (
        await db.execute(
            select(PlatformInvite).where(
                and_(
                    PlatformInvite.email == email,
                    PlatformInvite.accepted_at.is_(None),
                    PlatformInvite.revoked_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise InvitePendingError()

    invite = PlatformInvite(
        email=email,
        role=role,
        invited_by=invited_by,
        expires_at=datetime.now(UTC) + timedelta(days=_TTL_DAYS),
    )
    db.add(invite)
    await db.flush()
    invite_id = invite.id

    # PAR-D H5: stage the invite email in the outbox (same tx as the invite row).
    # The Supabase calls (invite_user_by_email + app_metadata write) happen out
    # of band in the worker, which writes supabase_user_id back onto this invite
    # row on success. PAR-D M1: no commit here — the route owns the transaction.
    # PAR-A C2: app_metadata (service-role-only writable) carries the invite id.
    await enqueue_invite_email(
        db,
        email=email,
        app_metadata={"platform_invite_id": str(invite_id), "platform_role": role.value},
        writeback={"table": "platform_invites", "id": str(invite_id)},
    )
    # Audit coverage (same tx — route owns the commit). target_id is the invite id.
    await write_audit_event(
        db,
        actor_id=invited_by,
        action="platform_invite.create",
        target_type="invite",
        target_id=invite_id,
        scope="platform",
        after={"email": email, "role": role.value},
    )
    return invite


async def revoke_platform_invite(db: AsyncSession, *, invite_id: UUID, actor_id: UUID) -> None:
    invite = (
        await db.execute(
            select(PlatformInvite).where(PlatformInvite.id == invite_id).with_for_update()
        )
    ).scalar_one_or_none()
    if invite is None:
        return  # idempotent: revoking an unknown/already-deleted invite is a 204 no-op
    # Capture the before-payload from the loaded row BEFORE mutating/deleting it.
    before = {"email": invite.email, "role": invite.role.value}
    if invite.accepted_at is not None:
        # ACCEPTED invite → "clear" it: delete the record only so it drops off
        # the invites list. The invitee is now a REAL, confirmed platform user;
        # we deliberately do NOT delete their Supabase auth identity here (that
        # would orphan a live account). No Supabase call on this branch. 204.
        await db.delete(invite)
        await write_audit_event(
            db,
            actor_id=actor_id,
            action="platform_invite.clear",
            target_type="invite",
            target_id=invite_id,
            scope="platform",
            before=before,
        )
        await db.commit()
        return
    if invite.revoked_at is not None:
        return  # already revoked — idempotent no-op, skip duplicate Supabase cleanup
    invite.revoked_at = datetime.now(UTC)
    # Audit row in the SAME tx as the revoke — this fn self-commits, so the
    # event MUST be written before the commit below.
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_invite.revoke",
        target_type="invite",
        target_id=invite_id,
        scope="platform",
        before=before,
    )
    await db.commit()

    # Best-effort: delete the unconfirmed Supabase auth user by the id we
    # captured at invite creation (O(1); no global list_users scan).
    if invite.supabase_user_id is not None:
        cfg = get_settings()
        sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
        sb_user_id = str(invite.supabase_user_id)
        # PAR-D L6: best-effort, but NOT silent. A failed delete leaves an
        # unconfirmed auth.users orphan; log it at WARN so it's visible (and
        # reconcilable) rather than swallowed by suppress(Exception).
        try:
            await asyncio.wait_for(
                asyncio.to_thread(lambda: sb.auth.admin.delete_user(sb_user_id)),
                timeout=cfg.supabase_timeout_sec,
            )
        except (TimeoutError, AuthApiError, AuthRetryableError, httpx.HTTPError) as e:
            _log.warning(
                "supabase_invite_user_delete_failed",
                supabase_user_id=sb_user_id,
                invite_id=str(invite_id),
                error=str(e),
            )


async def list_platform_invites(
    db: AsyncSession,
    *,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[PlatformInvite], str | None]:
    from ..core.pagination import encode_cursor

    stmt = select(PlatformInvite).order_by(
        PlatformInvite.created_at.desc(), PlatformInvite.id.desc()
    )
    if cursor is not None:
        ts, rid = cursor
        stmt = stmt.where(tuple_(PlatformInvite.created_at, PlatformInvite.id) < (ts, rid))
    stmt = stmt.limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last.created_at, last.id)
        rows = rows[:limit]
    return rows, next_cursor
