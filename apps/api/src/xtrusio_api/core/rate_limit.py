"""SlowAPI rate limiter wired to Valkey (Redis protocol).

PAR-A H8: single storage backend in dev AND prod — Valkey via the ``redis://``
URL scheme (the ``limits`` library treats Valkey as Redis). No in-memory
fallback, no hybrid; one code path so tests exercise the same limiter the
request path uses.

Limit values are tuned for the perimeter:
  - ``/signup`` and ``/invites/accept`` are IP-keyed (caller may be
    unauthenticated).
  - ``/onboarding/tenants`` is user-keyed (caller is always authenticated).
  - Authenticated catch-all is user-keyed (RL-1, wired below).

The limiter is a singleton — :mod:`main` registers it on ``app.state``,
wires the SlowAPI exception handler, AND installs ``SlowAPIMiddleware`` so the
user-keyed ``default_limits`` catch-all fires on every (non-exempt, non
explicitly-limited) authenticated route. Routes pull the singleton and apply
``@limiter.limit(...)`` decorators for their explicit per-route limits (slowapi
requires a ``request`` parameter on the wrapped route to identify the call).

RL-3 (proxy-trust): :func:`_client_ip` derives the client IP. By default it
trusts ONLY the socket peer and ignores ``X-Forwarded-For`` (correct when the
app is directly exposed, and for dev/tests). When the deployment sits behind N
trusted proxy/CDN hops, set ``RATE_LIMIT_TRUSTED_PROXY_HOPS=N`` and the IP is
read from the (N+1)-th XFF entry counted FROM THE RIGHT — the address the
outermost trusted proxy actually observed — never a blindly-trusted leftmost
client-supplied header (which an attacker could forge to mint unlimited
buckets). PROD OPERATOR NOTE: pair this with uvicorn's
``--forwarded-allow-ips=<proxy egress IP(s)>`` so a direct attacker cannot
inject a forged XFF that the app would honour.

SIGN-IN / FORGOT-PASSWORD POSTURE (RL-4, operator requirement — DOC ONLY):
Sign-in and forgot-password run browser → Supabase GoTrue DIRECTLY (the SPA
uses supabase-js; FastAPI is not in that path), so slowapi cannot rate-limit
them — there is no FastAPI request to intercept. Fronting them through a
FastAPI proxy is a larger architecture change, out of scope here. The
production posture for those flows is: rely on Supabase GoTrue's project-level
auth rate limits, and in the Supabase dashboard enable CAPTCHA (Auth → Bot &
Abuse Protection) and leaked-password protection (Auth → Passwords). This must
be configured by the operator; the application cannot enforce it.
"""

from __future__ import annotations

from fastapi import Request
from jose import jwt
from jose.exceptions import JOSEError
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import get_settings
from .logging import get_logger

_log = get_logger(__name__)

# Per-route limit specs (PAR-A section 4.2 H8). The authenticated catch-all rate is
# read from settings (``AUTHED_CATCHALL_RATE`` env, default "120/minute") so an
# operator can tune the ceiling without a code change; the module constant
# below mirrors the default purely for the existing config-shape test.
SIGNUP_RATE = "5/hour"
INVITE_ACCEPT_RATE = "10/hour"
ONBOARDING_RATE = "5/hour"
AUTHED_CATCHALL_RATE = "60/minute"


def _client_ip(request: Request) -> str:
    """Derive the client IP, honouring trusted-proxy hops (RL-3).

    ``RATE_LIMIT_TRUSTED_PROXY_HOPS == 0`` (default): trust only the socket
    peer via slowapi's ``get_remote_address`` (which itself falls back to
    ``127.0.0.1`` when ``request.client`` is unset, e.g. in-process ASGI
    tests). ``X-Forwarded-For`` is IGNORED — a directly-exposed app must never
    trust a client-supplied header.

    ``hops == N > 0``: the request traverses N trusted proxies, each appending
    the address it saw to the RIGHT of ``X-Forwarded-For``. The real client is
    therefore the (N+1)-th entry counted from the right. We never read the
    leftmost entry, which is fully attacker-controlled. If XFF is missing or
    too short to contain the expected hop (misconfig / direct hit that slipped
    past ``--forwarded-allow-ips``), we fall back to the socket peer — fail
    safe to the single, un-spoofable bucket rather than an attacker-chosen one.
    """
    hops = get_settings().rate_limit_trusted_proxy_hops
    if hops <= 0:
        return get_remote_address(request)
    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return get_remote_address(request)
    # Right-to-left: the rightmost entry is what the nearest proxy saw; index
    # ``hops`` from the right (0-based) is the address the OUTERMOST trusted
    # proxy observed — i.e. the real client when exactly ``hops`` trusted
    # proxies sit in front of us.
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if len(parts) >= hops + 1:
        return parts[-(hops + 1)]
    return get_remote_address(request)


def _authed_default_key(request: Request) -> str:
    """Key func for the authenticated catch-all default limit (RL-1).

    The catch-all is evaluated by ``SlowAPIMiddleware`` BEFORE the route's
    ``Depends(require_authenticated)`` runs, so ``request.state.identity`` is
    not yet populated — we cannot read a post-auth verified identity here.
    Instead we key on the JWT ``sub`` decoded from the bearer token WITHOUT
    cryptographic verification.

    Why unverified is acceptable here: this key only chooses a counting bucket,
    not an authorization decision. A forged/garbage token still 401s at the
    auth dependency, so it can never reach the work the limit protects; the
    worst an attacker does by varying ``sub`` is spread their own requests
    across buckets — and the independent per-IP layer (proxy-trust-aware) still
    bounds that. Unauthenticated / unparseable requests fall back to the client
    IP so the catch-all is never bypassable by simply omitting the header.
    """
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        try:
            sub = jwt.get_unverified_claims(token).get("sub")
            if sub:
                return f"user:{sub}"
        except JOSEError:
            # Malformed token → fall through to IP. The auth dep will 401 it.
            _log.debug("authed_catchall_key_unparseable_token")
    return _client_ip(request)


# The singleton limiter — created at import time so route decorators can
# reference it. Storage URI + the catch-all rate are read from settings.
#
# RL-1: the previously-dead authenticated catch-all is wired here as a DEFAULT
# limit, applied to every route that has NO explicit ``@limiter.limit``
# decorator (slowapi's ``SlowAPIMiddleware`` skips default limits for any route
# already present in ``_route_limits`` — so SIGNUP_RATE / INVITE_ACCEPT_RATE /
# ONBOARDING_RATE are NOT clobbered) and that is not exempted (health probes
# are exempted in main.py via ``@limiter.exempt``).
#
# slowapi builds the default-limit LimitGroup with the limiter's MAIN
# ``key_func``, so we set that to ``_authed_default_key`` to make the catch-all
# user-keyed. This does not change the IP-keyed routes: ``_authed_default_key``
# returns the client IP when there is no bearer token, and ``/signup`` and
# ``/invites/accept`` callers are unauthenticated (tokenless) → they still key
# by IP exactly as before. ``/onboarding`` overrides with its own user key_func.
limiter = Limiter(
    key_func=_authed_default_key,
    default_limits=[get_settings().authed_catchall_rate],
    storage_uri=get_settings().valkey_url,
    # No in-memory fallback — single backend in dev AND prod (PAR-A locked
    # decision section 14). If Valkey is unreachable, callers see 500s; that's the
    # explicit signal to fix infra, not a silent fall-back to a forgettable
    # in-memory counter.
    in_memory_fallback_enabled=False,
)
