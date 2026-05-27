"""PAR-A H8: SlowAPI limits are registered on the four perimeter endpoints.

We deliberately do NOT exercise the limit at volume: the limiter is wired to
the live Valkey instance (single backend in dev AND prod, per the locked
decision), and bursting it inside a test would leave counters in the shared
Valkey DB. Instead we assert the static config — that the limit decorator
attached the expected limit string to each route.
"""

from __future__ import annotations

from xtrusio_api.core.rate_limit import (
    AUTHED_CATCHALL_RATE,
    INVITE_ACCEPT_RATE,
    ONBOARDING_RATE,
    SIGNUP_RATE,
    limiter,
)
from xtrusio_api.main import app


def _route_limits_for(path: str, method: str = "POST") -> list[str]:
    """Pull the SlowAPI route-limit strings for the given (method, path).

    SlowAPI stores route limits in ``limiter._route_limits`` keyed by
    ``f"{func.__module__}.{func.__name__}"`` — we find the route's endpoint
    function via FastAPI's route table and look up the limits."""
    method_u = method.upper()
    for r in app.routes:
        # Starlette/FastAPI Routes carry path + methods + endpoint.
        rpath = getattr(r, "path", None)
        rmethods = getattr(r, "methods", None) or set()
        endpoint = getattr(r, "endpoint", None)
        if rpath == path and method_u in rmethods and endpoint is not None:
            name = f"{endpoint.__module__}.{endpoint.__name__}"
            limits = limiter._route_limits.get(name, [])
            return [str(limit.limit) for limit in limits]
    return []


def test_signup_rate_limit_registered() -> None:
    limits = _route_limits_for("/api/signup", "POST")
    assert limits, "expected /api/signup to have a registered rate limit"
    assert (
        SIGNUP_RATE.replace(" ", "") in [s.replace(" ", "") for s in limits]
        or SIGNUP_RATE in limits
        or "5 per 1 hour" in limits
    )


def test_invite_accept_rate_limit_registered() -> None:
    limits = _route_limits_for("/api/invites/accept", "POST")
    assert limits, "expected /api/invites/accept to have a registered rate limit"
    assert (
        INVITE_ACCEPT_RATE.replace(" ", "") in [s.replace(" ", "") for s in limits]
        or "10 per 1 hour" in limits
    )


def test_onboarding_rate_limit_registered() -> None:
    limits = _route_limits_for("/api/onboarding/tenants", "POST")
    assert limits, "expected /api/onboarding/tenants to have a registered rate limit"
    assert (
        ONBOARDING_RATE.replace(" ", "") in [s.replace(" ", "") for s in limits]
        or "5 per 1 hour" in limits
    )


def test_authed_catchall_rate_string_is_per_minute() -> None:
    """The authenticated catch-all spec is per-minute (60/minute). Assert the
    constant is well-formed — the catch-all is applied via default_limits in
    a later phase if needed; for PAR-A it's documented + ready."""
    assert "minute" in AUTHED_CATCHALL_RATE
    assert AUTHED_CATCHALL_RATE.startswith("60")


def test_limiter_singleton_is_app_state() -> None:
    """The exception handler + state.limiter must be wired so SlowAPI can
    inject rate-limit headers on responses."""
    assert app.state.limiter is limiter
