"""PAR-A C1: adversarial tests for the hardened JWT verification path.

Every test mints a Supabase-shaped token with one claim/header deliberately
wrong, hits a JWT-gated endpoint, and asserts a 401. The shared fixtures
(jwks_keypair + the conftest monkeypatch on _fetch_jwks) wire the verifier
to a test-only RSA key so we can issue signed tokens locally.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from jose import jwt
from xtrusio_api.core.config import get_settings
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


# /api/me requires require_authenticated → goes through the JWT verifier.
_PROBE_PATH = "/api/me"


def _mint(
    *,
    jwks_keypair: dict[str, Any],
    sub: UUID,
    alg: str = "RS256",
    aud: str | None = "authenticated",
    iss: str | None = None,
    exp_offset_sec: int = 3600,
    iat_offset_sec: int = 0,
    drop_claims: tuple[str, ...] = (),
    headers_override: dict[str, Any] | None = None,
) -> str:
    """Mint a JWT with deliberate deviations. ``drop_claims`` is applied
    POST-payload-build (used to test missing-claim 401 paths)."""
    cfg = get_settings()
    now = int(time.time())
    if iss is None:
        iss = f"{cfg.supabase_url.rstrip('/')}/auth/v1"
    payload: dict[str, Any] = {
        "sub": str(sub),
        "aud": aud,
        "iss": iss,
        "role": "authenticated",
        "iat": now + iat_offset_sec,
        "exp": now + exp_offset_sec,
        "user_metadata": {},
        "app_metadata": {},
    }
    for c in drop_claims:
        payload.pop(c, None)
    headers = {"kid": jwks_keypair["kid"], **(headers_override or {})}
    token: str = jwt.encode(payload, jwks_keypair["private_pem"], algorithm=alg, headers=headers)
    return token


async def _probe(http_client: AsyncClient, token: str) -> int:
    r = await http_client.get(_PROBE_PATH, headers={"Authorization": f"Bearer {token}"})
    return r.status_code


async def test_es256_forged_alg_in_header_rejected(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    existing_super_admin: PlatformUser,
) -> None:
    """A token whose header ``alg`` doesn't match its actual signature/key is
    rejected. ES256 is an accepted algorithm (Supabase's default), but this
    token *claims* ES256 in the header while being RSA-signed under an RSA JWKS
    key — so verification fails and we 401. (Pre-PAR-A the verifier picked
    ``alg`` from the JWKS doc, ignoring the header entirely.)"""
    # Mint a token with the header alg overridden to ES256 (the body is still
    # RSA-signed; the header-vs-signature mismatch is what we're checking).
    bad = _mint(
        jwks_keypair=jwks_keypair,
        sub=existing_super_admin.id,
        headers_override={"alg": "ES256"},
    )
    assert await _probe(http_client, bad) == 401


async def test_missing_iss_rejected(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    existing_super_admin: PlatformUser,
) -> None:
    bad = _mint(jwks_keypair=jwks_keypair, sub=existing_super_admin.id, drop_claims=("iss",))
    assert await _probe(http_client, bad) == 401


async def test_wrong_iss_rejected(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    existing_super_admin: PlatformUser,
) -> None:
    bad = _mint(
        jwks_keypair=jwks_keypair,
        sub=existing_super_admin.id,
        iss="https://attacker.example.com/auth/v1",
    )
    assert await _probe(http_client, bad) == 401


async def test_missing_aud_rejected(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    existing_super_admin: PlatformUser,
) -> None:
    bad = _mint(jwks_keypair=jwks_keypair, sub=existing_super_admin.id, drop_claims=("aud",))
    assert await _probe(http_client, bad) == 401


async def test_wrong_aud_rejected(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    existing_super_admin: PlatformUser,
) -> None:
    bad = _mint(jwks_keypair=jwks_keypair, sub=existing_super_admin.id, aud="other-project")
    assert await _probe(http_client, bad) == 401


async def test_expired_rejected(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    existing_super_admin: PlatformUser,
) -> None:
    bad = _mint(jwks_keypair=jwks_keypair, sub=existing_super_admin.id, exp_offset_sec=-60)
    assert await _probe(http_client, bad) == 401


async def test_missing_sub_rejected(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    existing_super_admin: PlatformUser,
) -> None:
    bad = _mint(jwks_keypair=jwks_keypair, sub=existing_super_admin.id, drop_claims=("sub",))
    assert await _probe(http_client, bad) == 401


async def test_missing_iat_rejected(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    existing_super_admin: PlatformUser,
) -> None:
    """C1 adds iat to the required-claims list."""
    bad = _mint(jwks_keypair=jwks_keypair, sub=existing_super_admin.id, drop_claims=("iat",))
    assert await _probe(http_client, bad) == 401


async def test_unknown_kid_rejected(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    existing_super_admin: PlatformUser,
) -> None:
    bad = _mint(
        jwks_keypair=jwks_keypair,
        sub=existing_super_admin.id,
        headers_override={"kid": "nope-unknown-key"},
    )
    assert await _probe(http_client, bad) == 401


async def test_happy_path_still_accepted(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    """Sanity gate: a token with the full canonical claim set (via the
    shared ``make_jwt`` fixture, which now includes ``iss``) still succeeds.
    Catches regressions in the hardening itself."""
    token = make_jwt(sub=existing_super_admin.id)
    r = await http_client.get(_PROBE_PATH, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


async def test_unknown_user_with_valid_jwt_still_401(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Defense-in-depth: a valid (signed, all-claim-correct) token whose
    ``sub`` doesn't map to a row in our DB returns 401 (not 200)."""
    token = make_jwt(sub=uuid4())
    r = await http_client.get(_PROBE_PATH, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
