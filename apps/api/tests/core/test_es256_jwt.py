"""ES256 JWT acceptance — guards the regression where the verifier was pinned to
RS256 only and 401'd every real Supabase login (this project's JWKS serves an
ES256 / P-256 EC key). Calls ``_decode_jwt`` directly with a genuine ES256 token
(no DB, no user lookup needed)."""

from __future__ import annotations

import base64
import time
from typing import Any
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from jose import jwt
from xtrusio_api.core import auth as auth_mod
from xtrusio_api.core.config import get_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")

# CWE-209: 401 details must be STABLE OPAQUE codes, never raw JOSE/JWKS text.
# Substrings that would betray a verbose leak if they ever appeared in a 401
# body (library/internal names or the JWKS host marker).
_LEAK_MARKERS = ("jwks", "jose", "jwt", "http://", "https://", "traceback", "supabase")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.mark.no_jwks_patch
async def test_es256_token_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    priv = ec.generate_private_key(ec.SECP256R1())
    nums = priv.public_key().public_numbers()
    kid = "es256-test-key"
    jwks = {
        "keys": [
            {
                "kid": kid,
                "kty": "EC",
                "crv": "P-256",
                "alg": "ES256",
                "use": "sig",
                "x": _b64url(nums.x.to_bytes(32, "big")),
                "y": _b64url(nums.y.to_bytes(32, "big")),
            }
        ]
    }

    async def _fake_uncached(url: str) -> dict[str, Any]:
        return jwks

    auth_mod._JWKS_CACHE.clear()
    monkeypatch.setattr(auth_mod, "_fetch_jwks_uncached", _fake_uncached)

    cfg = get_settings()
    sub = str(uuid4())
    now = int(time.time())
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    token = jwt.encode(
        {
            "sub": sub,
            "aud": "authenticated",
            "iss": f"{cfg.supabase_url.rstrip('/')}/auth/v1",
            "role": "authenticated",
            "iat": now,
            "exp": now + 3600,
        },
        pem,
        algorithm="ES256",
        headers={"kid": kid},
    )

    payload = await auth_mod._decode_jwt(token)
    assert payload["sub"] == sub
    assert payload["aud"] == "authenticated"


def _assert_opaque(detail: object) -> None:
    """The 401 detail is one of our stable codes and leaks no internals."""
    assert isinstance(detail, str)
    assert detail in (auth_mod._CODE_INVALID_TOKEN, auth_mod._CODE_JWKS_UNAVAILABLE)
    lowered = detail.lower()
    for marker in _LEAK_MARKERS:
        assert marker not in lowered, f"401 detail leaked internal marker {marker!r}: {detail!r}"


async def test_garbage_token_yields_opaque_invalid_token() -> None:
    """A non-JWT string fails header decode → opaque ``invalid_token``, never
    the raw JOSE exception text."""
    with pytest.raises(HTTPException) as exc:
        await auth_mod._decode_jwt("this-is-not-a-jwt")
    assert exc.value.status_code == 401
    assert exc.value.detail == auth_mod._CODE_INVALID_TOKEN
    _assert_opaque(exc.value.detail)


async def test_bad_signature_yields_opaque_invalid_token(make_jwt: object) -> None:
    """A structurally-valid token whose signature doesn't verify against the
    (autouse-patched test) JWKS fails ``jwt.decode`` → opaque ``invalid_token``."""
    # Mint a token with a kid the autouse JWKS knows ("test-key-1") but sign it
    # with a DIFFERENT key so signature verification fails inside jwt.decode.
    priv = ec.generate_private_key(ec.SECP256R1())
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cfg = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "aud": "authenticated",
            "iss": f"{cfg.supabase_url.rstrip('/')}/auth/v1",
            "role": "authenticated",
            "iat": now,
            "exp": now + 3600,
        },
        pem,
        algorithm="ES256",
        headers={"kid": "test-key-1"},
    )
    with pytest.raises(HTTPException) as exc:
        await auth_mod._decode_jwt(token)
    assert exc.value.status_code == 401
    _assert_opaque(exc.value.detail)


@pytest.mark.no_jwks_patch
async def test_jwks_fetch_failure_yields_opaque_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the JWKS fetch fails, the client sees the distinct opaque
    ``token_verification_unavailable`` code — never the (host-leaking) httpx
    error text."""
    auth_mod._JWKS_CACHE.clear()

    async def _boom(url: str) -> dict[str, Any]:
        raise httpx.ConnectError("connection refused to jwks host https://leak.example")

    monkeypatch.setattr(auth_mod, "_fetch_jwks_uncached", _boom)

    # A well-formed ES256 header so we get past header/alg/kid checks to the
    # JWKS fetch. The body content is irrelevant — the fetch fails first.
    priv = ec.generate_private_key(ec.SECP256R1())
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cfg = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "aud": "authenticated",
            "iss": f"{cfg.supabase_url.rstrip('/')}/auth/v1",
            "iat": now,
            "exp": now + 3600,
        },
        pem,
        algorithm="ES256",
        headers={"kid": "unknown-kid"},
    )
    with pytest.raises(HTTPException) as exc:
        await auth_mod._decode_jwt(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == auth_mod._CODE_JWKS_UNAVAILABLE
    _assert_opaque(exc.value.detail)
