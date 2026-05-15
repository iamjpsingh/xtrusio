"""Platform invites: create / list / revoke."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
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
        await asyncio.wait_for(asyncio.to_thread(_call), timeout=cfg.supabase_timeout_sec)
    except TimeoutError as e:
        await db.rollback()
        raise EmailProviderUnavailableError() from e
    except Exception as e:
        await db.rollback()
        raise EmailProviderUnavailableError() from e

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

    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
    invite_email = invite.email

    def _revoke_auth_user() -> None:
        for u in sb.auth.admin.list_users():
            if (
                getattr(u, "email", None) == invite_email
                and getattr(u, "email_confirmed_at", None) is None
            ):
                sb.auth.admin.delete_user(u.id)

    with contextlib.suppress(Exception):
        await asyncio.wait_for(
            asyncio.to_thread(_revoke_auth_user),
            timeout=cfg.supabase_timeout_sec,
        )


async def list_platform_invites(db: AsyncSession, *, limit: int = 50) -> list[PlatformInvite]:
    rows = (
        (
            await db.execute(
                select(PlatformInvite).order_by(PlatformInvite.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)
