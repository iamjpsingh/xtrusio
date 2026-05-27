"""SlowAPI rate limiter wired to Valkey (Redis protocol).

PAR-A H8: single storage backend in dev AND prod — Valkey via the ``redis://``
URL scheme (the ``limits`` library treats Valkey as Redis). No in-memory
fallback, no hybrid; one code path so tests exercise the same limiter the
request path uses.

Limit values are tuned for the perimeter:
  - ``/signup`` and ``/invites/accept`` are IP-keyed (caller may be
    unauthenticated).
  - ``/onboarding/tenants`` is user-keyed (caller is always authenticated).
  - Authenticated catch-all is user-keyed.

The limiter is a singleton — :mod:`main` registers it on ``app.state`` and
wires the SlowAPI exception handler. Routes pull the singleton and apply
``@limiter.limit(...)`` decorators (slowapi requires a ``request`` parameter
on the wrapped route to identify the call).
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from .auth import AuthIdentity
from .config import get_settings

# Per-route limit specs (PAR-A §4.2 H8).
SIGNUP_RATE = "5/hour"
INVITE_ACCEPT_RATE = "10/hour"
ONBOARDING_RATE = "5/hour"
AUTHED_CATCHALL_RATE = "60/minute"


def _ip_key(request: Request) -> str:
    """Key by client IP. SlowAPI's ``get_remote_address`` falls back to
    ``127.0.0.1`` when no ``request.client`` is set (ASGI in-process tests)."""
    return get_remote_address(request)


def _user_key(request: Request) -> str:
    """Key by authenticated ``user_id`` published on ``request.state.identity``
    by the auth dependency. Falls back to client IP if the dep did not fire
    (e.g. an unauthenticated request — that path would 401 before reaching
    the limiter check in practice, but the fallback keeps the key_func total).
    """
    identity: AuthIdentity | None = getattr(request.state, "identity", None)
    if identity is not None:
        return f"user:{identity.user_id}"
    return get_remote_address(request)


# The singleton limiter — created at import time so route decorators can
# reference it. Storage URI is read from settings lazily.
limiter = Limiter(
    key_func=_ip_key,
    storage_uri=get_settings().valkey_url,
    # No in-memory fallback — single backend in dev AND prod (PAR-A locked
    # decision §14). If Valkey is unreachable, callers see 500s; that's the
    # explicit signal to fix infra, not a silent fall-back to a forgettable
    # in-memory counter.
    in_memory_fallback_enabled=False,
)
