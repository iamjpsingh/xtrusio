"""RLS test helpers — run queries as the `authenticated` role with a synthetic auth.uid()."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal


@asynccontextmanager
async def as_user(user_id: UUID) -> AsyncIterator[AsyncSession]:
    """Execute statements as `authenticated` with auth.uid() returning user_id."""
    async with SessionLocal() as s:
        await s.execute(
            text(
                "SELECT set_config('request.jwt.claims', "
                ":claims, true), set_config('role', 'authenticated', true)"
            ),
            {"claims": '{"sub": "' + str(user_id) + '", "role": "authenticated"}'},
        )
        await s.execute(text("SET LOCAL ROLE authenticated"))
        try:
            yield s
        finally:
            await s.rollback()


RlsAs = Callable[[UUID], AbstractAsyncContextManager[AsyncSession]]


@pytest_asyncio.fixture
async def rls_as() -> RlsAs:
    """Return a callable that opens an RLS-scoped session for a given user_id."""
    return as_user
