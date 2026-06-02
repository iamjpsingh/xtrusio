"""Signup orchestration: gate check + existence-aware Supabase email branching.

The toggle is the HARD gate: if ``signups_enabled`` is False, signup is
rejected outright (403) — no auth user is created and no email is sent.

When enabled, ``create_signup_user`` looks up the email in ``auth.users``
(owner DB session) and branches so the *email the person receives* matches
their real account state — the GitHub/Slack pattern:

* new email             → ``auth.sign_up``              → "Confirm signup"
* exists & unconfirmed  → ``auth.resend(type="signup")``→ re-send confirm
* exists & confirmed    → ``auth.reset_password_email`` → "Reset password"
  (the "you already have an account" nudge, landing on ``/reset-password``)

SECURITY — non-enumeration (audit C2 / PAR-A #25) is PRESERVED:
This deliberately re-adds server-side existence detection that #63 removed,
BUT the client/API response is **identical** across all three branches —
``create_signup_user`` returns ``None`` every time and the route always
answers ``202 confirm_email_sent``. The ONLY observable difference is which
email Supabase sends, which is not visible to an unauthenticated probe of the
API. So there is no oracle for an attacker to enumerate registered emails.

The confirmation/resend link redirect is pinned to ``WEB_APP_URL`` via
``options.email_redirect_to`` (the reset link to ``WEB_APP_URL/reset-password``)
so the email lands back on OUR SPA instead of inheriting the Supabase project's
Site URL. NOTE: GoTrue only honours these redirects if the URL is in the
project's **Redirect URLs** allow-list; otherwise it silently falls back to the
Site URL.

Every Supabase call is wrapped in
``asyncio.wait_for(asyncio.to_thread(...), timeout)`` → a transport/timeout
failure surfaces as ``EmailProviderUnavailableError`` (route → 502).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx
from gotrue.errors import AuthApiError, AuthError, AuthRetryableError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from supabase import create_client

from ..core.config import get_settings
from .platform_settings import is_signups_enabled


class SignupsDisabledError(Exception):
    pass


class EmailProviderUnavailableError(Exception):
    pass


async def lookup_auth_user(db: AsyncSession, email: str) -> tuple[bool, bool]:
    """Look up ``email`` in ``auth.users`` via the owner DB session.

    Returns ``(exists, confirmed)``:

    * ``exists``    — an ``auth.users`` row matches (case-insensitive).
    * ``confirmed`` — that row has a non-null ``email_confirmed_at``.

    Factored into its own function so tests can patch it (mirrors how
    ``is_signups_enabled`` is patched), making the ``create_signup_user``
    branches deterministic without real ``auth.users`` rows. The request DB
    connection runs as the owner role, which can read GoTrue's ``auth.users``
    table (same access pattern as ``core.auth``'s email lookup).
    """
    row = (
        await db.execute(
            text(
                "SELECT email_confirmed_at FROM auth.users "
                "WHERE lower(email) = lower(:email) LIMIT 1"
            ),
            {"email": email},
        )
    ).first()
    if row is None:
        return (False, False)
    return (True, row[0] is not None)


async def _send_via_supabase(
    send: Callable[[], object], *, timeout_sec: float, swallow_api_errors: bool = False
) -> None:
    """Run a blocking Supabase email call off-thread with a timeout.

    Failure handling is uniform so the OUTCOME never depends on the email's
    account state (non-enumeration):

    * transport/timeout (``TimeoutError`` / ``AuthRetryableError`` / ``httpx``)
      → ``EmailProviderUnavailableError`` (route → 502).
    * GoTrue 4xx (``AuthApiError`` — e.g. an already-confirmed ``resend`` or a
      per-email send throttle): with ``swallow_api_errors`` (the blind resend
      path) it is SWALLOWED so the endpoint returns an identical 202 and cannot
      leak whether the email is new / unconfirmed / confirmed; otherwise → 502.
    * any other GoTrue error (``AuthError``) → 502.

    Without this, an ``AuthApiError`` would escape as a 500 — both breaking the
    graceful-502 contract AND re-opening a 500-vs-202 enumeration oracle on the
    unauthenticated resend endpoint (the very thing this slice protects).

    ``send`` returns the Supabase response, which we discard.
    """
    try:
        await asyncio.wait_for(asyncio.to_thread(send), timeout=timeout_sec)
    except (TimeoutError, AuthRetryableError, httpx.HTTPError) as e:
        raise EmailProviderUnavailableError() from e
    except AuthApiError as e:
        if swallow_api_errors:
            return
        raise EmailProviderUnavailableError() from e
    except AuthError as e:
        raise EmailProviderUnavailableError() from e


async def create_signup_user(*, db: AsyncSession, email: str, password: str) -> None:
    """Send the right confirmation/reset email for ``email``'s account state.

    Hard-gated by ``signups_enabled``: disabled → ``SignupsDisabledError``
    (no auth user created, no email). Enabled → branch on the ``auth.users``
    lookup (new / unconfirmed / confirmed) per the module docstring.

    Returns ``None`` in EVERY branch: the route handler never branches on the
    outcome and the response shape is identical for new vs. unconfirmed vs.
    confirmed — this is the non-enumeration guarantee (see module docstring).
    """
    if not await is_signups_enabled(db):
        raise SignupsDisabledError()

    cfg = get_settings()
    exists, confirmed = await lookup_auth_user(db, email)

    # ANON-key client: ``sign_up``/``resend``/``reset_password_email`` are the
    # public, browser-equivalent flows. The service-role key would bypass the
    # behaviour we rely on, so the anon key is intentional.
    sb = create_client(cfg.supabase_url, cfg.supabase_anon_key)

    if not exists:
        # New email → native confirm-signup email.
        await _send_via_supabase(
            lambda: sb.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {"email_redirect_to": cfg.web_app_url},
                }
            ),
            timeout_sec=cfg.supabase_timeout_sec,
        )
    elif not confirmed:
        # Exists but never confirmed → re-send the confirmation email.
        await _send_via_supabase(
            lambda: sb.auth.resend(
                {
                    "type": "signup",
                    "email": email,
                    "options": {"email_redirect_to": cfg.web_app_url},
                }
            ),
            timeout_sec=cfg.supabase_timeout_sec,
        )
    else:
        # Already a real account → send a password-reset email (the "you
        # already have an account" nudge), landing on /reset-password.
        reset_redirect = f"{cfg.web_app_url.rstrip('/')}/reset-password"
        await _send_via_supabase(
            lambda: sb.auth.reset_password_email(email, {"redirect_to": reset_redirect}),
            timeout_sec=cfg.supabase_timeout_sec,
        )


async def resend_signup_confirmation(*, db: AsyncSession, email: str) -> None:
    """Resend the signup-confirmation email for ``email``.

    Used by ``POST /api/signup/resend`` (e.g. the sign-in "resend verification"
    nudge and the sign-up success-screen resend button). Hard-gated by
    ``signups_enabled`` like ``create_signup_user``. Always returns ``None``
    and never reveals whether the email exists: GoTrue ``resend`` raises an
    ``AuthApiError`` for an already-confirmed (or otherwise ineligible) email,
    so ``swallow_api_errors=True`` collapses that to the identical 202 — only a
    genuine transport/timeout failure surfaces as 502 (non-enumeration).
    """
    if not await is_signups_enabled(db):
        raise SignupsDisabledError()

    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_anon_key)
    await _send_via_supabase(
        lambda: sb.auth.resend(
            {
                "type": "signup",
                "email": email,
                "options": {"email_redirect_to": cfg.web_app_url},
            }
        ),
        timeout_sec=cfg.supabase_timeout_sec,
        swallow_api_errors=True,
    )
