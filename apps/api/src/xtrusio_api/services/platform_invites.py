"""Platform invites: create / list / revoke."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from supabase import create_client

from ..core.config import get_settings
from ..models.platform_invite import PlatformInvite
from ..models.platform_user import PlatformRole, PlatformUser

_TTL_DAYS = 7


class UserExistsError(Exception):
    pass


class InvitePendingError(Exception):
    pass


class InviteAlreadyAcceptedError(Exception):
    pass


class EmailProviderUnavailableError(Exception):
    pass


async def create_platform_invite(
    db: AsyncSession,
    *,
    email: str,
    role: PlatformRole,
    invited_by: UUID,
) -> PlatformInvite:
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

    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def _call() -> Any:
        return sb.auth.admin.invite_user_by_email(  # type: ignore[call-arg]
            email,
            data={"platform_invite_id": str(invite_id), "platform_role": role.value},
        )

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_call), timeout=cfg.supabase_timeout_sec)
    except TimeoutError as e:
        await db.rollback()
        raise EmailProviderUnavailableError() from e
    except Exception as e:
        await db.rollback()
        raise EmailProviderUnavailableError() from e

    sb_user_id: str | None = getattr(getattr(result, "user", None), "id", None)
    if isinstance(sb_user_id, str):
        try:
            invite.supabase_user_id = UUID(sb_user_id)
        except ValueError:
            invite.supabase_user_id = None

    await db.commit()
    await db.refresh(invite)
    return invite


async def revoke_platform_invite(db: AsyncSession, *, invite_id: UUID) -> None:
    invite = (
        await db.execute(select(PlatformInvite).where(PlatformInvite.id == invite_id))
    ).scalar_one_or_none()
    if invite is None:
        return  # idempotent: revoking an unknown/already-deleted invite is a 204 no-op
    if invite.accepted_at is not None:
        raise InviteAlreadyAcceptedError()
    if invite.revoked_at is not None:
        return  # already revoked — idempotent no-op, skip duplicate Supabase cleanup
    invite.revoked_at = datetime.now(UTC)
    await db.commit()

    # Best-effort: delete the unconfirmed Supabase auth user by the id we
    # captured at invite creation (O(1); no global list_users scan).
    if invite.supabase_user_id is not None:
        cfg = get_settings()
        sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
        sb_user_id = str(invite.supabase_user_id)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                asyncio.to_thread(lambda: sb.auth.admin.delete_user(sb_user_id)),
                timeout=cfg.supabase_timeout_sec,
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
        stmt = stmt.where(
            or_(
                PlatformInvite.created_at < ts,
                and_(PlatformInvite.created_at == ts, PlatformInvite.id < rid),
            )
        )
    stmt = stmt.limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last.created_at, last.id)
        rows = rows[:limit]
    return rows, next_cursor
