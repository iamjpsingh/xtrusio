"""Signup orchestration: gate check + native Supabase ``sign_up``.

The toggle is the HARD gate: if ``signups_enabled`` is False, signup is
rejected outright (403) — no auth user is created. When enabled, we use the
ANON-key client's ``auth.sign_up`` (the native browser flow), which:

* creates the unconfirmed ``auth.users`` row, AND
* triggers Supabase's confirmation email, AND
* natively OBFUSCATES an already-registered email (non-enumeration) — the
  response shape is identical whether the email is new or already taken, so
  there is no oracle for an attacker.

Because ``sign_up`` handles non-enumeration itself, the old
``admin.create_user`` + ``EmailTakenError`` detection + password-reset
fall-back are gone. A transport/timeout failure surfaces as
``EmailProviderUnavailableError`` (route → 502).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
from gotrue.errors import AuthRetryableError
from sqlalchemy.ext.asyncio import AsyncSession

from supabase import create_client

from ..core.config import get_settings
from .platform_settings import is_signups_enabled

if TYPE_CHECKING:
    from gotrue.types import AuthResponse


class SignupsDisabledError(Exception):
    pass


class EmailProviderUnavailableError(Exception):
    pass


async def create_signup_user(*, db: AsyncSession, email: str, password: str) -> None:
    """Natively sign up an unconfirmed Supabase auth user.

    Hard-gated by ``signups_enabled``: disabled → ``SignupsDisabledError``
    (no auth user created). Enabled → ``auth.sign_up`` via the ANON-key
    client, which sends the confirmation email and obfuscates an
    already-registered email (non-enumeration) on Supabase's side.

    Returns ``None``: the route handler never branches on the outcome; the
    response shape is identical for a new vs. already-registered email.
    """
    if not await is_signups_enabled(db):
        raise SignupsDisabledError()

    cfg = get_settings()
    # ANON-key client: ``sign_up`` is the public, browser-equivalent flow.
    # Using the service-role key here would bypass the non-enumeration
    # behaviour we rely on, so the anon key is intentional.
    sb = create_client(cfg.supabase_url, cfg.supabase_anon_key)

    def _call() -> AuthResponse:
        return sb.auth.sign_up({"email": email, "password": password})

    try:
        await asyncio.wait_for(asyncio.to_thread(_call), timeout=cfg.supabase_timeout_sec)
    except (TimeoutError, AuthRetryableError, httpx.HTTPError) as e:
        # Transport / timeout failure: the email could not be requested.
        # Surfaced as 502 by the route. (A genuine "email already registered"
        # is NOT an error here — sign_up returns 200 with an obfuscated user.)
        raise EmailProviderUnavailableError() from e
