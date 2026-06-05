"""RL-1 / RL-2 / RL-3 rate-limit hardening.

Covers the three audit findings closed in this slice:

* RL-1 (``authed-catchall-dead``): the user-keyed authenticated catch-all is
  now WIRED via ``default_limits`` + ``SlowAPIMiddleware``. We assert it (a)
  trips for a single token over the ceiling, (b) is per-user (a different token
  is unaffected), (c) exempts health probes, and (d) does not clobber an
  explicit per-route limit.
* RL-2 (``ip-keyed-ratelimit-bypass-and-email-bombing``): the per-email
  throttle is tested in ``test_signup_email_throttle.py`` (signup path).
* RL-3 (``ratelimit-ip-key-spoof``): proxy-trust key derivation is unit-tested
  here with a fake Request — default 0 hops uses the socket peer; a configured
  hop count derives the validated rightmost-untrusted XFF entry.

These tests build their OWN Limiter + tiny FastAPI app so they can pick a low,
deterministic ceiling and exercise real middleware behaviour WITHOUT bursting
the production limiter's shared Valkey counters (the autouse
``_disable_rate_limiter`` fixture only touches the production singleton).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from jose import jwt
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from xtrusio_api.core import rate_limit as rl
from xtrusio_api.core.config import get_settings

# NOTE: no module-level ``pytestmark`` asyncio mark — the RL-3 proxy-trust tests
# below are SYNC (they call ``_client_ip`` directly), so the async tests carry
# the mark individually via the ``_async`` alias to avoid the "async mark on a
# sync function" warning.
_async = pytest.mark.asyncio(loop_scope="session")


def _make_token(sub: str) -> str:
    """An UNSIGNED-content JWT — the catch-all key func reads ``sub`` via
    ``get_unverified_claims``, so a throwaway HS256 token is enough here."""
    token: str = jwt.encode({"sub": sub}, "irrelevant-secret", algorithm="HS256")
    return token


def _build_app(default_limit: str) -> FastAPI:
    """A tiny app mirroring main.py's wiring: one user-keyed catch-all default,
    one explicitly-limited route, and an exempt health probe."""
    limiter = Limiter(
        key_func=rl._authed_default_key,
        default_limits=[default_limit],
        storage_uri="memory://",
        in_memory_fallback_enabled=False,
    )
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/api/thing")
    async def thing(request: Request) -> dict[str, str]:
        return {"ok": "thing"}

    @app.post("/api/explicit")
    @limiter.limit("1000/minute")
    async def explicit(request: Request) -> dict[str, str]:
        return {"ok": "explicit"}

    @app.get("/health/live")
    async def live(request: Request) -> dict[str, str]:
        return {"ok": "live"}

    limiter.exempt(live)  # type: ignore[no-untyped-call]
    return app


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@_async
async def test_catchall_trips_after_ceiling_for_one_user() -> None:
    app = _build_app("3/minute")
    token = _make_token(str(uuid.uuid4()))
    h = {"Authorization": f"Bearer {token}"}
    async with await _client(app) as c:
        codes = [(await c.get("/api/thing", headers=h)).status_code for _ in range(4)]
    # First 3 pass, the 4th trips the 3/minute ceiling.
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


@_async
async def test_catchall_is_per_user_not_global() -> None:
    app = _build_app("2/minute")
    a = {"Authorization": f"Bearer {_make_token(str(uuid.uuid4()))}"}
    b = {"Authorization": f"Bearer {_make_token(str(uuid.uuid4()))}"}
    async with await _client(app) as c:
        # Burn user A's budget.
        assert (await c.get("/api/thing", headers=a)).status_code == 200
        assert (await c.get("/api/thing", headers=a)).status_code == 200
        assert (await c.get("/api/thing", headers=a)).status_code == 429
        # User B has a SEPARATE bucket — unaffected by A's burst.
        assert (await c.get("/api/thing", headers=b)).status_code == 200
        assert (await c.get("/api/thing", headers=b)).status_code == 200
        assert (await c.get("/api/thing", headers=b)).status_code == 429


@_async
async def test_catchall_exempts_health_probe() -> None:
    app = _build_app("1/minute")
    async with await _client(app) as c:
        # Far more than the ceiling — health probe is exempt, never 429s.
        for _ in range(5):
            assert (await c.get("/health/live")).status_code == 200


@_async
async def test_catchall_does_not_clobber_explicit_route_limit() -> None:
    """A route with its OWN @limiter.limit("1000/minute") is NOT subject to the
    low catch-all default — the middleware skips routes already in
    ``_route_limits``."""
    app = _build_app("1/minute")
    token = _make_token(str(uuid.uuid4()))
    h = {"Authorization": f"Bearer {token}"}
    async with await _client(app) as c:
        codes = [(await c.post("/api/explicit", headers=h)).status_code for _ in range(5)]
    # All succeed — the explicit 1000/minute applies, not the 1/minute default.
    assert codes == [200, 200, 200, 200, 200]


@_async
async def test_unauthenticated_request_falls_back_to_ip_bucket() -> None:
    """No bearer token → the catch-all keys by client IP (never bypassable by
    simply omitting the header)."""
    app = _build_app("2/minute")
    async with await _client(app) as c:
        codes = [(await c.get("/api/thing")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# --- RL-3: proxy-trust key derivation (unit, fake Request) ---------------


def _fake_request(*, peer: str | None, xff: str | None) -> Request:
    """Build a minimal Starlette Request with a chosen socket peer + XFF."""
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/api/thing",
        "headers": headers,
        "client": (peer, 12345) if peer is not None else None,
    }
    return Request(scope)


def test_proxy_trust_default_uses_socket_peer_ignores_xff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default 0 hops: XFF is ignored entirely, the socket peer wins (an
    attacker cannot mint buckets by spoofing the header)."""
    monkeypatch.setattr(get_settings(), "rate_limit_trusted_proxy_hops", 0)
    req = _fake_request(peer="203.0.113.7", xff="1.1.1.1, 2.2.2.2")
    assert rl._client_ip(req) == "203.0.113.7"


def test_proxy_trust_one_hop_uses_rightmost_untrusted_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With 1 trusted hop, the client is the 2nd-from-right XFF entry (the
    address the trusted proxy observed), NOT the forgeable leftmost value."""
    monkeypatch.setattr(get_settings(), "rate_limit_trusted_proxy_hops", 1)
    # Attacker-supplied leftmost "9.9.9.9"; trusted proxy appended the real
    # client "198.51.100.4"; the nearest proxy appended its own peer last.
    req = _fake_request(peer="10.0.0.1", xff="9.9.9.9, 198.51.100.4, 10.0.0.1")
    assert rl._client_ip(req) == "198.51.100.4"


def test_proxy_trust_two_hops_counts_from_right(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_trusted_proxy_hops", 2)
    req = _fake_request(peer="10.0.0.1", xff="9.9.9.9, 203.0.113.50, 10.0.0.2, 10.0.0.1")
    assert rl._client_ip(req) == "203.0.113.50"


def test_proxy_trust_short_xff_falls_back_to_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    """XFF too short for the configured hop count (misconfig / direct hit) →
    fail safe to the un-spoofable socket peer, not an attacker-chosen entry."""
    monkeypatch.setattr(get_settings(), "rate_limit_trusted_proxy_hops", 2)
    req = _fake_request(peer="203.0.113.7", xff="9.9.9.9")
    assert rl._client_ip(req) == "203.0.113.7"


def test_proxy_trust_missing_xff_falls_back_to_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_trusted_proxy_hops", 1)
    req = _fake_request(peer="203.0.113.7", xff=None)
    assert rl._client_ip(req) == "203.0.113.7"


def test_authed_default_key_uses_jwt_sub() -> None:
    sub = str(uuid.uuid4())
    req = _fake_request(peer="203.0.113.7", xff=None)
    # Inject the bearer header directly into the scope's header list.
    token = _make_token(sub)
    req2 = _fake_request(peer="203.0.113.7", xff=None)
    req2.scope["headers"] = [(b"authorization", f"Bearer {token}".encode())]
    assert rl._authed_default_key(req2) == f"user:{sub}"
    # No token → IP fallback.
    assert rl._authed_default_key(req) == "203.0.113.7"
