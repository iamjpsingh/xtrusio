"""Signup orchestration: gate check + Supabase Admin user creation."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from gotrue.errors import AuthApiError
from sqlalchemy.ext.asyncio import AsyncSession

from supabase import create_client

from ..core.config import get_settings
from .platform_settings import is_signups_enabled

if TYPE_CHECKING:
    from gotrue.types import UserResponse

# Stable gotrue error codes meaning "this email is already registered".
_EMAIL_TAKEN_CODES = frozenset({"email_exists", "user_already_exists"})


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

    def _call() -> UserResponse:
        return sb.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": False}
        )

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_call), timeout=cfg.supabase_timeout_sec)
    except TimeoutError as e:
        raise EmailProviderUnavailableError() from e
    except AuthApiError as e:
        if (e.code or "") in _EMAIL_TAKEN_CODES:
            raise EmailTakenError() from e
        raise

    if result.user is None:
        raise EmailProviderUnavailableError()
    return str(result.user.id)
