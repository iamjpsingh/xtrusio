"""Shared pytest fixtures for the api test suite."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.main import app
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _purge_test_data_around_session() -> AsyncIterator[None]:
    """Crash-proof cleanup: purge BEFORE the suite (removes any leftovers from a
    previously killed run) and AFTER it. The pre-sweep is the real guarantee —
    a killed run is always cleaned by the next run or `make test-clean`."""
    from tests._cleanup import purge_test_data

    await purge_test_data()
    yield
    await purge_test_data()


@pytest_asyncio.fixture(autouse=True)
async def _isolate_platform_settings() -> AsyncIterator[None]:
    """Snapshot the global platform_settings singleton before each test and
    restore it after, so tests never persistently mutate the operator's real
    config. Preserves whatever value the operator set (snapshot is taken live)."""
    async with SessionLocal() as s:
        snap = (
            await s.execute(
                text("SELECT signups_enabled, updated_by FROM platform_settings WHERE id = 1")
            )
        ).first()
    yield
    if snap is None:
        return
    async with SessionLocal() as s:
        cur = (
            await s.execute(
                text("SELECT signups_enabled, updated_by FROM platform_settings WHERE id = 1")
            )
        ).first()
        if cur is not None and (cur[0], cur[1]) != (snap[0], snap[1]):
            await s.execute(
                text(
                    "UPDATE platform_settings SET signups_enabled = :se, updated_by = :ub "
                    "WHERE id = 1"
                ),
                {"se": snap[0], "ub": snap[1]},
            )
            await s.commit()


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
def _patch_jwks(jwks_keypair: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest_asyncio.fixture(scope="session")
async def existing_super_admin() -> AsyncIterator[PlatformUser]:
    """The ONE super_admin the operator created via `make create-platform-owner`.

    Read-only: tests verify super-admin behaviour against this real row but
    NEVER create or delete a super_admin. If none exists the dependent tests
    skip (they never fail and never create one)."""
    async with SessionLocal() as s:
        row = (
            await s.execute(
                select(PlatformUser).where(PlatformUser.role == PlatformRole.SUPER_ADMIN).limit(1)
            )
        ).scalar_one_or_none()
    if row is None:
        pytest.skip(
            "No super_admin in the database — run "
            "`make create-platform-owner email=... password=...` first. "
            "Tests never create a super_admin."
        )
    yield row


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
    monkeypatch.setattr("xtrusio_api.services.platform_invites.create_client", _factory)
    monkeypatch.setattr("xtrusio_api.services.tenant_invites.create_client", _factory)
    yield mock_client
