"""PAR-B H7: JWKS rotation + stale-grace behaviour.

The verifier MUST:
  - refetch ONCE when a token's ``kid`` is not in the cached JWKS doc, so a
    Supabase key rotation does not 401 every request for a full TTL;
  - serve the stale cached doc if upstream is down AND the cached entry
    expired no more than ``jwks_stale_grace_sec`` ago (bounded outage
    tolerance).

These tests opt out of conftest's autouse ``_patch_jwks`` (which would
short-circuit the caching wrapper we want to test) via the
``@pytest.mark.no_jwks_patch`` marker. They then patch the lower layer
``_fetch_jwks_uncached`` to simulate upstream behaviour deterministically.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from xtrusio_api.core import auth as _auth_mod

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.no_jwks_patch,
]


@pytest.fixture(autouse=True)
def _clear_cache_around_test() -> Any:
    """Wipe the module-level cache before + after each test in this file
    so prior test state does not leak."""
    _auth_mod._JWKS_CACHE.clear()
    yield
    _auth_mod._JWKS_CACHE.clear()


async def test_unknown_kid_triggers_one_refetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the cached JWKS doesn't contain the kid the verifier needs, the
    second-chance refetch fires exactly once."""
    url = "https://example.test/jwks"

    calls = {"n": 0}
    docs = [
        {"keys": [{"kid": "old", "kty": "RSA", "alg": "RS256"}]},
        {"keys": [{"kid": "new", "kty": "RSA", "alg": "RS256"}]},
    ]

    async def _fake(_url: str) -> dict[str, Any]:
        i = calls["n"]
        calls["n"] += 1
        return docs[min(i, len(docs) - 1)]

    monkeypatch.setattr(_auth_mod, "_fetch_jwks_uncached", _fake)

    # First call populates the cache with the "old" doc.
    first = await _auth_mod._fetch_jwks(url)
    assert first["keys"][0]["kid"] == "old"
    assert calls["n"] == 1

    # Forcing a refresh (simulates the kid-not-found code path) returns
    # the new doc — exactly one extra upstream call.
    second = await _auth_mod._fetch_jwks(url, force_refresh=True)
    assert second["keys"][0]["kid"] == "new"
    assert calls["n"] == 2


async def test_stale_grace_serves_old_doc_when_upstream_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired-but-stale-grace-eligible cache entry should be served when
    upstream is down — a Supabase outage does not flip auth to 100% failure
    for ``jwks_stale_grace_sec``."""
    url = "https://example.test/jwks"
    cached_doc = {"keys": [{"kid": "k1", "kty": "RSA", "alg": "RS256"}]}
    # Seed the cache as just-expired.
    _auth_mod._JWKS_CACHE[url] = (cached_doc, time.time() - 5.0)

    async def _failing(_url: str) -> dict[str, Any]:
        raise httpx.ConnectError("simulated upstream outage")

    monkeypatch.setattr(_auth_mod, "_fetch_jwks_uncached", _failing)

    served = await _auth_mod._fetch_jwks(url)
    assert served is cached_doc, "stale-grace must return the cached doc"


async def test_stale_grace_gives_up_after_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the stale-grace window closes, upstream failure surfaces — we
    don't keep serving an indefinitely-stale JWKS."""
    from xtrusio_api.core.config import get_settings

    grace = get_settings().jwks_stale_grace_sec
    url = "https://example.test/jwks"
    cached_doc = {"keys": [{"kid": "k1", "kty": "RSA", "alg": "RS256"}]}
    # Seed the cache as expired BEYOND the stale-grace window.
    _auth_mod._JWKS_CACHE[url] = (cached_doc, time.time() - (grace + 10.0))

    async def _failing(_url: str) -> dict[str, Any]:
        raise httpx.ConnectError("simulated upstream outage")

    monkeypatch.setattr(_auth_mod, "_fetch_jwks_uncached", _failing)

    with pytest.raises(httpx.ConnectError):
        await _auth_mod._fetch_jwks(url)
