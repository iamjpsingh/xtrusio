"""Cold-start JWKS fetches must coalesce — one HTTP fetch even under N concurrent callers."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from xtrusio_api.core import auth as auth_mod

# Capture the real _fetch_jwks BEFORE any test fixture (including conftest's autouse
# _patch_jwks) has had a chance to monkey-patch it. This module is imported during
# collection, before fixtures fire — so this binds to the genuine coalescing wrapper.
_REAL_FETCH_JWKS = auth_mod._fetch_jwks

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_concurrent_cold_fetches_coalesce(monkeypatch: pytest.MonkeyPatch) -> None:
    # The autouse `_patch_jwks` fixture in tests/conftest.py replaces
    # `_fetch_jwks` (the wrapper) with a stub that bypasses our coalescing
    # primitive. Restore the real wrapper for this test only; monkeypatch
    # teardown will re-apply the autouse stub afterward.
    monkeypatch.setattr(auth_mod, "_fetch_jwks", _REAL_FETCH_JWKS)

    auth_mod._JWKS_CACHE.clear()
    auth_mod._JWKS_LOCKS.clear()

    calls = 0

    async def _slow_fetch_uncached(url: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {"keys": []}

    monkeypatch.setattr(auth_mod, "_fetch_jwks_uncached", _slow_fetch_uncached)

    results = await asyncio.gather(
        *[auth_mod._fetch_jwks("https://example.com/jwks") for _ in range(10)]
    )
    assert all(r == {"keys": []} for r in results)
    assert calls == 1, f"expected 1 underlying fetch under coalescing, got {calls}"
