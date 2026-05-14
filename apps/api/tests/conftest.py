"""Shared pytest fixtures for the api test suite."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.main import app
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Per-test session against the global engine."""
    async with SessionLocal() as session:
        yield session


def _b64url(data: bytes) -> str:
    """RFC 7515 base64url without padding."""
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.fixture(scope="session")
def jwks_keypair() -> dict[str, Any]:
    """Generate an RSA keypair once per test session; publish matching JWKS."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_numbers = private_key.public_key().public_numbers()
    n_bytes = pub_numbers.n.to_bytes((pub_numbers.n.bit_length() + 7) // 8, "big")
    e_bytes = pub_numbers.e.to_bytes((pub_numbers.e.bit_length() + 7) // 8, "big")
    kid = "test-key-1"
    jwks = {
        "keys": [
            {
                "kid": kid,
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": _b64url(n_bytes),
                "e": _b64url(e_bytes),
            }
        ]
    }
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return {"jwks": jwks, "private_pem": pem, "kid": kid}


@pytest.fixture(autouse=True)
def _patch_jwks(
    jwks_keypair: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replace the live JWKS fetcher with one that returns our test JWKS."""
    from xtrusio_api.core import auth as _auth_mod

    _auth_mod._JWKS_CACHE.clear()

    jwks: dict[str, Any] = jwks_keypair["jwks"]

    async def _fake_fetch(url: str) -> dict[str, Any]:
        return jwks

    monkeypatch.setattr(_auth_mod, "_fetch_jwks", _fake_fetch)


@pytest.fixture
def make_jwt(jwks_keypair: dict[str, Any]) -> Iterator[Callable[..., str]]:
    """Factory: mint a Supabase-shaped JWT signed with the test private key."""

    def _factory(
        *,
        sub: UUID,
        expired: bool = False,
        user_metadata: dict[str, Any] | None = None,
    ) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": str(sub),
            "aud": "authenticated",
            "role": "authenticated",
            "iat": now,
            "exp": now - 60 if expired else now + 3600,
            "user_metadata": user_metadata or {},
        }
        token: str = jwt.encode(
            payload,
            jwks_keypair["private_pem"],
            algorithm="RS256",
            headers={"kid": jwks_keypair["kid"]},
        )
        return token

    yield _factory


@pytest_asyncio.fixture
async def super_admin_user() -> AsyncIterator[PlatformUser]:
    """Insert a super_admin platform user; clean up rows on teardown."""
    user_id = uuid4()
    email = f"sa-{user_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(user_id), "email": email},
        )
        pu = PlatformUser(id=user_id, email=email, role=PlatformRole.SUPER_ADMIN, is_active=True)
        s.add(pu)
        await s.commit()
        await s.refresh(pu)
    try:
        yield pu
    finally:
        async with SessionLocal() as s:
            await s.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
            await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await s.commit()


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[AsyncClient]:
    """ASGI in-process client (no real network)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


@pytest.fixture
def mock_supabase_admin(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Replace the supabase client factory so tests never hit the real API."""
    mock_client = MagicMock()
    mock_client.auth.admin = MagicMock()

    def _factory(*_args: object, **_kwargs: object) -> MagicMock:
        return mock_client

    monkeypatch.setattr("xtrusio_api.services.signup.create_client", _factory)
    yield mock_client
