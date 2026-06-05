"""Per-email request throttle for the secure-signup endpoints (RL-2).

Background — the email-bombing gap this closes
================================================
``/api/signup`` and ``/api/signup/resend`` ALWAYS send an email when signups
are enabled (the secure, non-enumeration design: a confirm / resend / "you
already have an account" reset mail goes out regardless of account state, so
the API response can never be used to enumerate registered addresses).

The only abuse control was an IP-keyed slowapi limit (``SIGNUP_RATE`` =
5/IP/hour). An attacker who rotates source IPs (botnet, proxy pool, cloud
egress) collapses every request into a *fresh* per-IP bucket and can therefore
email-bomb a single known victim's inbox without limit. This module adds a
SECOND, independent ceiling keyed on the **normalized target email** so the
victim's address is throttled no matter which IP each request arrives from.
The two limits are defense-in-depth — both must pass.

Backed by Valkey (mirrors :mod:`perm_cache`'s ``redis.asyncio`` client).

CRITICAL — non-enumeration invariant
=====================================
This throttle counts REQUESTS PER EMAIL. It does **not** read ``auth.users``,
does **not** know or care whether the email belongs to a real account, and
behaves byte-identically for an existing, an unconfirmed, and a non-existent
address: the Nth request to a given email is rejected purely because N requests
were already made to THAT email in the window — never because of any account
state. The over-limit signal is a uniform HTTP ``429`` raised by the route
*before* the Supabase branch runs, so it fires the same for every email and
adds no observable difference between "this email exists" and "it doesn't".
It is therefore NOT an enumeration oracle. Do not add any account-state branch
to this code path.

Best-effort like ``perm_cache``: a Valkey outage degrades to "not throttled"
(logged at WARN) rather than failing the signup request closed — the per-IP
slowapi limit is still in force during such an outage.
"""

from __future__ import annotations

import hashlib

import redis.asyncio as aioredis

from .config import get_settings
from .logging import get_logger

_log = get_logger(__name__)
_client: aioredis.Redis | None = None

# Key namespace. Distinct prefix so the test-isolation cleanup can target it
# without touching ``perm:*`` keys in the shared Valkey instance.
_KEY_PREFIX = "signup_email"


def _get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        # Short timeouts so an unreachable Valkey fails fast into the tolerant
        # fallback below rather than hanging the signup request.
        _client = aioredis.from_url(
            get_settings().valkey_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client


async def close_email_throttle() -> None:
    """Close the module Valkey client (FastAPI lifespan shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _normalize(email: str) -> str:
    """Lowercase + strip the email so case/whitespace variants share a bucket.

    Mirrors the case-insensitive ``lower(email)`` lookup the signup service
    uses against ``auth.users``, so an attacker can't multiply their per-email
    budget by toggling case.
    """
    return email.strip().lower()


def _key(email: str) -> str:
    """SHA-256 of the normalized email, namespaced. Hashing keeps raw target
    addresses out of the Valkey keyspace (a shared, less-guarded store) while
    preserving a stable per-email bucket."""
    digest = hashlib.sha256(_normalize(email).encode("utf-8")).hexdigest()
    return f"{_KEY_PREFIX}:{digest}"


async def is_email_throttled(email: str) -> bool:
    """Atomically count this request against ``email`` and report over-limit.

    Returns ``True`` once the email has exceeded ``signup_email_max_per_window``
    requests within ``signup_email_window_sec`` — purely request-count based,
    never account-state based (see module docstring's non-enumeration invariant).

    The INCR+EXPIRE pair is pipelined; EXPIRE is set on the first increment
    (``count == 1``) so the window is a fixed sliding-from-first-request TTL.
    On any Valkey error we fail OPEN (return ``False``, log WARN) so a cache
    outage never takes signup down — the per-IP slowapi limit still applies.
    """
    settings = get_settings()
    key = _key(email)
    try:
        async with _get_client().pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = await pipe.execute()
        if count == 1 or ttl < 0:
            # First hit in this window (or a key with no TTL): (re)arm the
            # window. We never extend the TTL on later hits, so a burst can't
            # keep pushing the expiry out.
            await _get_client().expire(key, settings.signup_email_window_sec)
    except Exception as e:  # Valkey down must not break signup (fail open)
        _log.warning("signup_email_throttle_failed", error=str(e))
        return False
    return int(count) > settings.signup_email_max_per_window


async def clear_all() -> None:
    """Drop every signup-email throttle key. Test helper (per-test isolation),
    tolerant of a down Valkey so the suite runs whether or not Valkey is up."""
    try:
        client = _get_client()
        keys = [k async for k in client.scan_iter(match=f"{_KEY_PREFIX}:*")]
        if keys:
            await client.delete(*keys)
    except Exception as e:
        _log.warning("signup_email_throttle_clear_failed", error=str(e))
