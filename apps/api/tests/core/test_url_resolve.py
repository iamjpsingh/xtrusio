"""Tests for core.url_resolve — Vertex AI grounding redirect resolution.

Uses httpx's MockTransport, so no real network is hit. Verifies: redirect
proxies resolve to the real URL, non-grounding URLs pass through untouched (no
request made), HEAD-405 falls back to GET, failures/unescaped redirects return
the input, and batch resolution preserves order + skips non-grounding URLs.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
from xtrusio_api.core.url_resolve import (
    VERTEX_REDIRECT_HOST,
    is_grounding_redirect,
    resolve_grounding_url,
    resolve_grounding_urls,
)

_VERTEX = f"https://{VERTEX_REDIRECT_HOST}/grounding-api-redirect/TOKEN1"
_REAL = "https://example.com/the-real-article"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_is_grounding_redirect() -> None:
    assert is_grounding_redirect(_VERTEX) is True
    assert is_grounding_redirect("https://example.com/x") is False
    # host must match exactly, not as a substring sitting in the path
    assert is_grounding_redirect(f"https://evil.com/{VERTEX_REDIRECT_HOST}") is False
    assert is_grounding_redirect("not a url") is False


async def test_resolves_vertex_redirect_to_real_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == VERTEX_REDIRECT_HOST:
            return httpx.Response(302, headers={"Location": _REAL})
        return httpx.Response(200, text="ok")

    async with _client(handler) as c:
        assert await resolve_grounding_url(_VERTEX, client=c) == _REAL


async def test_non_grounding_url_passes_through_without_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    async with _client(handler) as c:
        assert await resolve_grounding_url(_REAL, client=c) == _REAL
    assert calls == 0  # real URLs are never touched — no network hop


async def test_head_405_falls_back_to_get() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == VERTEX_REDIRECT_HOST:
            if request.method == "HEAD":
                return httpx.Response(405)
            return httpx.Response(302, headers={"Location": _REAL})
        return httpx.Response(200, text="ok")

    async with _client(handler) as c:
        assert await resolve_grounding_url(_VERTEX, client=c) == _REAL


async def test_resolution_failure_returns_input() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    async with _client(handler) as c:
        assert await resolve_grounding_url(_VERTEX, client=c) == _VERTEX


async def test_redirect_that_never_leaves_proxy_returns_input() -> None:
    # Proxy answers 200 directly (no Location) → unresolved → keep the input.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="still on the proxy")

    async with _client(handler) as c:
        assert await resolve_grounding_url(_VERTEX, client=c) == _VERTEX


async def test_batch_preserves_order_and_skips_non_grounding() -> None:
    real2 = "https://docs.example.org/page"
    passthrough = "https://passthrough.example.com/a"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == VERTEX_REDIRECT_HOST:
            token = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(302, headers={"Location": _REAL if token == "T1" else real2})
        return httpx.Response(200)

    urls = [
        f"https://{VERTEX_REDIRECT_HOST}/grounding-api-redirect/T1",
        passthrough,
        f"https://{VERTEX_REDIRECT_HOST}/grounding-api-redirect/T2",
    ]
    async with _client(handler) as c:
        out = await resolve_grounding_urls(urls, client=c, concurrency=2)
    assert out == [_REAL, passthrough, real2]


async def test_batch_empty_returns_empty() -> None:
    assert await resolve_grounding_urls([]) == []
