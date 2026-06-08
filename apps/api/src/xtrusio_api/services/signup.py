"""Signup orchestration: gate check + existence-revealing Supabase branching.

The toggle is the HARD gate: if ``signups_enabled`` is False, signup is
rejected outright (403) — no auth user is created and no email is sent.

When enabled, ``create_signup_user`` looks up the email in ``auth.users``
(owner DB session) and branches into exactly two outcomes (Flow B — the
product owner deliberately chose CLARITY over enumeration-resistance):

* new email                     → ``auth.sign_up`` (creates the account and
  sends the "Confirm signup" verification email).
* exists (verified OR unverified, NOT distinguished) → ``EmailAlreadyExistsError``;
  NO account is created and NO email of ANY kind is sent. The route maps this
  to ``409 email_exists`` so the UI can say "this email already has an account"
  and offer a sign-in link.

This is an INTENTIONAL reversal of the old non-enumeration design: there is
now an observable 202-vs-409 difference between a new and an existing email,
and that is by design. Password-reset emails are sent ONLY from the
forgot-password flow now — signup never sends one.

The confirmation link redirect is pinned to ``WEB_APP_URL`` via
``options.email_redirect_to`` so the email lands back on OUR SPA instead of
inheriting the Supabase project's Site URL. NOTE: GoTrue only honours this
redirect if the URL is in the project's **Redirect URLs** allow-list;
otherwise it silently falls back to the Site URL.

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


class EmailAlreadyExistsError(Exception):
    """The submitted email already has an ``auth.users`` account.

    Raised by ``create_signup_user`` for an existing email (verified OR
    unverified — the two are NOT distinguished). The route maps this to
    ``409 email_exists``. No account is created and no email is sent.
    """


class EmailProviderUnavailableError(Exception):
    pass


async def lookup_auth_user(db: AsyncSession, email: str) -> tuple[bool, bool]:
    """Look up ``email`` in ``auth.users`` via the owner DB session.

    Returns ``(exists, confirmed)``:

    * ``exists``    — an ``auth.users`` row matches (case-insensitive).
    * ``confirmed`` — that row has a non-null ``email_confirmed_at``.

    Factored into its own function so tests can patch it (mirrors how
    ``is_signups_enabled`` is patched), making the ``create_signup_user``
    branch deterministic without real ``auth.users`` rows. The request DB
    connection runs as the owner role, which can read GoTrue's ``auth.users``
    table (same access pattern as ``core.auth``'s email lookup).

    Flow B only branches on ``exists`` — ``confirmed`` is returned for
    completeness/diagnostics but does NOT change the outcome (an existing
    unverified email is treated identically to an existing verified one).
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

    Failure handling:

    * transport/timeout (``TimeoutError`` / ``AuthRetryableError`` / ``httpx``)
      → ``EmailProviderUnavailableError`` (route → 502).
    * GoTrue 4xx (``AuthApiError`` — e.g. a per-email send throttle, or a
      ``resend`` for an already-confirmed address): with ``swallow_api_errors``
      (the ``/signup/resend`` path) it is SWALLOWED so the endpoint returns a
      uniform 202; otherwise → 502.
    * any other GoTrue error (``AuthError``) → 502.

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
    """Create the account for a NEW ``email``, or reject an EXISTING one.

    Hard-gated by ``signups_enabled``: disabled → ``SignupsDisabledError``
    (no auth user created, no email). Enabled → branch on the ``auth.users``
    lookup (Flow B):

    * new email     → ``auth.sign_up`` (creates the account + sends the
      verification email); returns ``None`` → route answers ``202``.
    * exists        → ``EmailAlreadyExistsError`` (no account, no email) →
      route answers ``409 email_exists``. Verified vs. unverified is NOT
      distinguished.
    """
    if not await is_signups_enabled(db):
        raise SignupsDisabledError()

    cfg = get_settings()
    exists, _confirmed = await lookup_auth_user(db, email)

    if exists:
        # Existing account (verified or not) → reject. No email is sent here;
        # a password reset is only ever sent from the forgot-password flow.
        raise EmailAlreadyExistsError()

    # New email → native confirm-signup email via the ANON-key client (the
    # public, browser-equivalent flow). The service-role key would bypass the
    # behaviour we rely on, so the anon key is intentional.
    sb = create_client(cfg.supabase_url, cfg.supabase_anon_key)
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


async def resend_signup_confirmation(*, db: AsyncSession, email: str) -> None:
    """Resend the signup-confirmation email for ``email``.

    Used by ``POST /api/signup/resend`` (e.g. the sign-up success-screen resend
    button). Hard-gated by ``signups_enabled`` like ``create_signup_user``.
    Always returns ``None``: GoTrue ``resend`` raises an ``AuthApiError`` for an
    already-confirmed (or otherwise ineligible) email, so ``swallow_api_errors``
    collapses that to a uniform 202 — only a genuine transport/timeout failure
    surfaces as 502.
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
