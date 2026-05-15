"""CORS preflight must succeed for the browser SPA origin.

The web app (Vite dev server on :5173) calls the API (:8000) cross-origin
with an `Authorization` header, which makes the browser send a preflight
`OPTIONS` request. Without CORS middleware the router answers 405 and every
`/api/me` poll from the AuthGuard is blocked.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from xtrusio_api.core.config import get_settings
from xtrusio_api.main import app


def test_preflight_allowed_origin_succeeds() -> None:
    origin = get_settings().cors_allow_origins[0]
    client = TestClient(app)
    response = client.options(
        "/api/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_preflight_disallowed_origin_has_no_allow_header() -> None:
    client = TestClient(app)
    response = client.options(
        "/api/me",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers
