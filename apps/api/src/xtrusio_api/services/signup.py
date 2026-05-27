"""Signup orchestration: gate check + Supabase Admin user creation.

PAR-A H8 (non-enumeration): the public response shape never distinguishes
"new email" from "email already exists". If the gotrue Admin API reports the
email is taken, we instead trigger a password-reset email (so the existing
account-holder still receives an actionable email — same UX surface). The
``EmailTakenError`` type is kept for internal branching but is NEVER raised
to a route handler.
"""

from __future__ import annotations

import asyncio
import logging
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

log = logging.getLogger(__name__)


class SignupsDisabledError(Exception):
    pass


class EmailTakenError(Exception):
    """Internal-only: signals the email is already in use. NEVER raised to a
    route handler — callers must catch it and fall back to a non-enumerating
    side-effect (e.g. send a password-reset email)."""


class EmailProviderUnavailableError(Exception):
    pass


async def _send_password_reset(*, email: str) -> None:
    """Non-enumerating fall-back when ``create_user`` reports the email is
    already taken: trigger a password-reset email so the legitimate
    account-holder still gets an actionable message in their inbox. We catch
    and *log* email-provider failures here — surfacing them as 502 would leak
    the "this email exists" signal we're trying to suppress."""
    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def _call() -> None:
        sb.auth.reset_password_for_email(email)

    try:
        await asyncio.wait_for(asyncio.to_thread(_call), timeout=cfg.supabase_timeout_sec)
    except Exception as e:
        # Intentional broad catch: the public response MUST NOT distinguish
        # "real email reset succeeded" from "we couldn't send anything", so we
        # swallow every failure mode (timeout, gotrue error, transport) and
        # only log server-side.
        log.warning("password_reset_send_failed", extra={"email_hash": hash(email), "err": str(e)})


async def create_signup_user(*, db: AsyncSession, email: str, password: str) -> None:
    """Create an unconfirmed Supabase auth user, or — if the email is already
    taken — silently send a password reset to the existing account.

    Returns ``None``: the route handler never branches on the outcome; the
    response shape is identical for both paths (non-enumeration).
    """
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
            # Non-enumerating fallback: send a password reset (no exception
            # surfaces to the route — caller emits the same 202 either way).
            await _send_password_reset(email=email)
            return
        raise

    if result.user is None:
        raise EmailProviderUnavailableError()
    return
