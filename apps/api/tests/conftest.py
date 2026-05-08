"""Shared pytest fixtures for the api test suite."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Iterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.config import get_settings
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.main import app
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

SETTINGS = get_settings()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Per-test session against the global engine."""
    async with SessionLocal() as session:
        yield session


@pytest.fixture
def make_jwt() -> Iterator[Callable[..., str]]:
    """Factory to mint a Supabase-shaped JWT for a given sub UUID."""

    def _factory(*, sub: UUID, expired: bool = False) -> str:
        now = int(time.time())
        payload = {
            "sub": str(sub),
            "aud": "authenticated",
            "role": "authenticated",
            "iat": now,
            "exp": now - 60 if expired else now + 3600,
        }
        token: str = jwt.encode(payload, SETTINGS.supabase_jwt_secret, algorithm="HS256")
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
