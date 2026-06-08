"""Resolve Vertex AI / Gemini grounding redirect URLs to their real destination.

Gemini's Google-Search grounding returns each cited source as a SIGNED REDIRECT
proxy on ``vertexaisearch.cloud.google.com`` (``…/grounding-api-redirect/<token>``),
NOT the source URL — and those tokens expire. So when we persist grounding
citations we resolve the redirect once, at ingest, and store the real URL. The
caller should keep the original redirect + the grounding ``web.title`` as
fallbacks, so a failed resolve is never fatal.

Resolution is one network hop per URL, so :func:`resolve_grounding_urls` runs a
batch concurrently with a bounded pool. A URL that is NOT a grounding redirect is
returned untouched with NO network call, so it's safe to pass a whole mixed
citation list. Any failure (timeout, redirect loop, a redirect that never leaves
the proxy host) returns the input unchanged.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from urllib.parse import urlsplit

import httpx

from .logging import get_logger

_log = get_logger(__name__)

# The host Gemini / Vertex AI grounding returns its redirect proxies on.
VERTEX_REDIRECT_HOST = "vertexaisearch.cloud.google.com"

_DEFAULT_TIMEOUT_SEC = 5.0
_DEFAULT_CONCURRENCY = 8


def is_grounding_redirect(url: str) -> bool:
    """True if ``url`` is a Vertex AI grounding redirect proxy.

    Matches on the exact host (not a substring), so a real source URL that merely
    mentions the host in its path/query is never misclassified.
    """
    try:
        return urlsplit(url).hostname == VERTEX_REDIRECT_HOST
    except ValueError:
        return False


async def _resolve_one(url: str, client: httpx.AsyncClient, timeout_sec: float) -> str:
    """Follow ``url``'s redirect(s) and return the final URL.

    Returns ``url`` unchanged when it isn't a grounding redirect (no network
    call), or when resolution fails / never escapes the proxy host — so the
    caller always gets a usable link.
    """
    if not is_grounding_redirect(url):
        return url
    try:
        # HEAD is cheapest; some endpoints reject it (405) — fall back to a
        # streamed GET whose body we never read (we only want the final URL).
        resp = await client.head(url, follow_redirects=True, timeout=timeout_sec)
        final = str(resp.url)
        if resp.status_code >= 400 or is_grounding_redirect(final):
            async with client.stream("GET", url, follow_redirects=True, timeout=timeout_sec) as r:
                final = str(r.url)
        return final if not is_grounding_redirect(final) else url
    except httpx.HTTPError:
        _log.warning("grounding_url_resolve_failed", url=url)
        return url


async def resolve_grounding_url(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
) -> str:
    """Resolve a single grounding redirect to its real URL (see module docstring).

    Pass a shared ``client`` when resolving many URLs; omit it for a one-off and a
    short-lived client is created for the call.
    """
    if client is not None:
        return await _resolve_one(url, client, timeout_sec)
    async with httpx.AsyncClient() as owned:
        return await _resolve_one(url, owned, timeout_sec)


async def resolve_grounding_urls(
    urls: Sequence[str],
    *,
    client: httpx.AsyncClient | None = None,
    concurrency: int = _DEFAULT_CONCURRENCY,
    timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
) -> list[str]:
    """Resolve a batch of URLs concurrently, preserving input order.

    Non-grounding URLs pass through untouched (no network), so a full mixed
    citation list is fine to pass. At most ``concurrency`` resolves run at once.
    """
    if not urls:
        return []
    if client is None:
        async with httpx.AsyncClient() as owned:
            return await resolve_grounding_urls(
                urls, client=owned, concurrency=concurrency, timeout_sec=timeout_sec
            )
    sem = asyncio.Semaphore(concurrency)

    async def _guarded(u: str) -> str:
        async with sem:
            return await _resolve_one(u, client, timeout_sec)

    gathered = await asyncio.gather(*(_guarded(u) for u in urls))
    return [str(x) for x in gathered]
