"""PAR-B C3: assert the engine pushed ``statement_timeout`` and
``idle_in_transaction_session_timeout`` server-settings into the asyncpg
connection. We pull the values back via ``SHOW`` from a live session and
check they match what settings.py advertises."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.config import get_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_statement_timeout_is_pushed(db_session: AsyncSession) -> None:
    """The asyncpg connection should report the configured statement_timeout."""
    expected_ms = get_settings().db_statement_timeout_ms
    row = (await db_session.execute(text("SHOW statement_timeout"))).first()
    assert row is not None
    raw = row[0]
    # Postgres returns "5s" / "5000ms" / "0" depending on the unit it picked.
    if raw.endswith("ms"):
        actual_ms = int(raw[:-2])
    elif raw.endswith("s"):
        actual_ms = int(float(raw[:-1]) * 1000)
    elif raw == "0":
        actual_ms = 0
    else:
        actual_ms = int(raw)
    assert actual_ms == expected_ms, f"statement_timeout: expected {expected_ms}ms, got {raw}"


async def test_idle_in_tx_timeout_is_pushed(db_session: AsyncSession) -> None:
    expected_ms = get_settings().db_idle_in_tx_timeout_ms
    row = (await db_session.execute(text("SHOW idle_in_transaction_session_timeout"))).first()
    assert row is not None
    raw = row[0]
    if raw.endswith("ms"):
        actual_ms = int(raw[:-2])
    elif raw.endswith("s"):
        actual_ms = int(float(raw[:-1]) * 1000)
    elif raw == "0":
        actual_ms = 0
    else:
        actual_ms = int(raw)
    assert actual_ms == expected_ms


async def test_application_name_set(db_session: AsyncSession) -> None:
    """``application_name`` is set so DB-side observability surfaces the
    process owner. Helps when triaging slow queries in Supabase."""
    row = (await db_session.execute(text("SHOW application_name"))).first()
    assert row is not None
    assert row[0] == "xtrusio-api"
