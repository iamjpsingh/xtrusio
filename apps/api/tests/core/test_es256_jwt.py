"""ES256 JWT acceptance — guards the regression where the verifier was pinned to
RS256 only and 401'd every real Supabase login (this project's JWKS serves an
ES256 / P-256 EC key). Calls ``_decode_jwt`` directly with a genuine ES256 token
(no DB, no user lookup needed)."""

from __future__ import annotations

import base64
import time
from typing import Any
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt
from xtrusio_api.core import auth as auth_mod
from xtrusio_api.core.config import get_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")


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
