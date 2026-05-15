"""Signup orchestration: gate check + Supabase Admin user creation."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from supabase import create_client

from ..core.config import get_settings
from .platform_settings import is_signups_enabled


class SignupsDisabledError(Exception):
    pass


class EmailTakenError(Exception):
    pass


class EmailProviderUnavailableError(Exception):
    pass


async def create_signup_user(*, db: AsyncSession, email: str, password: str) -> str:
    """Create an unconfirmed Supabase auth user. Returns the user id."""
    if not await is_signups_enabled(db):
        raise SignupsDisabledError()

    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def _call() -> Any:
        return sb.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": False}
        )

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_call), timeout=cfg.supabase_timeout_sec)
    except TimeoutError as e:
        raise EmailProviderUnavailableError() from e
    except Exception as e:
        # supabase-py 2.x raises on duplicate email — string match is brittle but works for now.
        if "already" in str(e).lower():
            raise EmailTakenError() from e
        raise

    if result.user is None:
        raise EmailProviderUnavailableError()
    return str(result.user.id)
