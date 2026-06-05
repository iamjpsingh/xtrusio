"""HTTP security-headers middleware (CWE-693/1021).

Two layers of assertion:
  1. Against the REAL app (``/health/live`` — no auth, no DB) so we prove the
     middleware is actually wired into the production stack and stamps the
     baseline headers on a live response.
  2. Against a tiny standalone Starlette app wrapping the middleware directly so
     we can parametrize ``is_prod`` and prove HSTS is sent ONLY in prod and that
     the docs paths are exempted from CSP while still hardened otherwise.

DB-free by construction: this module never imports ``SessionLocal`` / touches
``auth.users`` and never requests the Supabase fixtures, so it is NOT tagged
``requires_supabase`` and runs on the ephemeral-Postgres / Supabase-free job.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from xtrusio_api.core.middleware import (
    _API_CSP,
    _DOCS_PATHS,
    _HSTS_VALUE,
    SecurityHeadersMiddleware,
)
from xtrusio_api.main import app as real_app

pytestmark = pytest.mark.asyncio(loop_scope="session")

_BASELINE = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


async def test_real_app_stamps_baseline_headers_on_health() -> None:
    """The middleware is wired into the live stack — /health/live carries the
    baseline headers + the strict API CSP (it is not a docs path)."""
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        res = await c.get("/health/live")
    assert res.status_code == 200
    for name, value in _BASELINE.items():
        assert res.headers.get(name) == value
    assert res.headers.get("Content-Security-Policy") == _API_CSP


def _probe_app(*, is_prod: bool) -> Starlette:
    async def _ok(_request: object) -> PlainTextResponse:
        return PlainTextResponse("ok")

    routes = [
        Route("/probe", _ok),
        Route("/docs", _ok),
        Route("/redoc", _ok),
        Route("/openapi.json", _ok),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(SecurityHeadersMiddleware, is_prod=is_prod)
    return app


async def test_hsts_present_only_in_prod() -> None:
    transport = ASGITransport(app=_probe_app(is_prod=True))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        res = await c.get("/probe")
    assert res.headers.get("Strict-Transport-Security") == _HSTS_VALUE
    # Baseline headers still present in prod.
    for name, value in _BASELINE.items():
        assert res.headers.get(name) == value


async def test_hsts_absent_in_non_prod() -> None:
    transport = ASGITransport(app=_probe_app(is_prod=False))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        res = await c.get("/probe")
    assert "Strict-Transport-Security" not in res.headers
    # Baseline headers + CSP still applied off the docs path.
    for name, value in _BASELINE.items():
        assert res.headers.get(name) == value
    assert res.headers.get("Content-Security-Policy") == _API_CSP


@pytest.mark.parametrize("path", sorted(_DOCS_PATHS))
async def test_docs_paths_are_exempt_from_csp(path: str) -> None:
    """CSP is skipped on the docs UI paths so Swagger/ReDoc keep loading their
    CDN assets + inline scripts, while the non-CSP hardening still applies."""
    transport = ASGITransport(app=_probe_app(is_prod=False))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        res = await c.get(path)
    assert "Content-Security-Policy" not in res.headers
    # The other hardening headers must still be set on the docs paths.
    for name, value in _BASELINE.items():
        assert res.headers.get(name) == value


async def test_non_docs_path_gets_strict_csp() -> None:
    transport = ASGITransport(app=_probe_app(is_prod=False))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        res = await c.get("/probe")
    assert res.headers.get("Content-Security-Policy") == _API_CSP
