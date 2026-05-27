"""Async SQLAlchemy engine + session factory.

PAR-B C3: explicit pool sizing, recycle, ``statement_timeout`` and
``idle_in_transaction_session_timeout`` server-settings, plus a SQLAlchemy
``checkin`` listener that resets the request-scoped GUCs PAR-C lifts up
(``app.actor_id``, ``app.bypass_priv_escalation``). When ``DATABASE_URL``
points at the Supavisor pooler, the app-side pool collapses to ``NullPool``
(Supavisor owns the real pool) and asyncpg's prepared-statement cache is
disabled (Supavisor transaction-mode routes statements across physical
connections so reused PREPARE names would collide).

The branch is deliberately on the hostname rather than a flag so an operator
who flips ``DATABASE_URL`` between pooler and direct does not need to touch
code or a second env var.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from .config import get_settings


class Base(AsyncAttrs, DeclarativeBase):
    """Declarative base for all ORM models."""


_settings = get_settings()


def _is_pooler_dsn(url: str) -> bool:
    """``True`` when the URL host is the Supavisor pooler.

    Supavisor hostnames look like ``aws-N-<region>.pooler.supabase.com``; the
    substring match is intentionally loose so the SESSION-mode (5432) and
    TRANSACTION-mode (6543) endpoints both take the same branch.
    """
    return ".pooler.supabase.com" in url


def _build_engine_kwargs() -> dict[str, Any]:
    """Compose pool + connect args from settings + DSN shape.

    Server-side timeouts (``statement_timeout``, etc.) are NOT passed via
    asyncpg ``server_settings`` because Supavisor session-mode ignores them
    at connect (the pooler reuses upstream sessions whose settings predate
    our connection). Instead, the ``connect`` event listener below explicitly
    ``SET``s them after the connection is established — Supavisor honours
    post-connect SET statements on the same backend session.
    """
    if _is_pooler_dsn(_settings.database_url):
        # Supavisor owns the pool. Disable both caches so transaction-mode
        # statement routing does not collide on prepared-statement names.
        return {
            "poolclass": NullPool,
            "future": True,
            "connect_args": {
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
        }
    # Direct Postgres: app-side sized pool with recycle + pre_ping.
    return {
        "pool_size": _settings.db_pool_size,
        "max_overflow": _settings.db_max_overflow,
        "pool_recycle": _settings.db_pool_recycle_sec,
        "pool_timeout": _settings.db_pool_timeout_sec,
        "pool_pre_ping": True,
        "pool_reset_on_return": "rollback",
        "future": True,
    }


engine = create_async_engine(_settings.database_url, **_build_engine_kwargs())


@event.listens_for(engine.sync_engine, "connect")
def _set_session_settings(dbapi_conn: Any, _record: Any) -> None:
    """Apply server-side timeouts + application_name on every fresh
    connection.

    Why an event listener instead of asyncpg ``server_settings``: Supavisor's
    session-mode pooler ignores ``server_settings`` passed at connect time
    (the upstream session predates our connection) but honours subsequent
    ``SET`` statements on the same backend session. Direct-connection DSNs
    also accept post-connect SETs — so one path covers both topologies.
    """
    cur = dbapi_conn.cursor()
    try:
        # asyncpg's prepared-statement path rejects multi-statement SQL, so
        # issue each SET as its own statement.
        cur.execute(f"SET statement_timeout = {_settings.db_statement_timeout_ms}")
        cur.execute(
            f"SET idle_in_transaction_session_timeout = {_settings.db_idle_in_tx_timeout_ms}"
        )
        cur.execute("SET application_name = 'xtrusio-api'")
    finally:
        cur.close()


@event.listens_for(engine.sync_engine, "checkin")
def _reset_session_gucs(dbapi_conn: Any, _record: Any) -> None:
    """Wipe request-scoped GUCs before a connection returns to the pool.

    PAR-C lifts ``_set_actor`` into a request-scoped FastAPI dependency that
    writes ``app.actor_id`` via ``SET LOCAL``; the LOCAL scope is bounded by
    the surrounding transaction, but a read-only route that never commits
    relies on this listener to clear actor state before the connection is
    handed to the next request. The same applies to
    ``app.bypass_priv_escalation`` (the reconciler-only bypass GUC PAR-C
    isolates to its own DB role).

    On the pooler ``NullPool`` branch this fires too but is effectively a
    no-op since every checkin closes the underlying connection.
    """
    cur = dbapi_conn.cursor()
    try:
        # asyncpg's sync cursor rejects multi-statement SQL — issue each
        # RESET separately. Custom GUCs that were never set are a no-op for
        # RESET in Postgres, so we don't need to gate on prior SET.
        cur.execute("RESET app.actor_id")
        cur.execute("RESET app.bypass_priv_escalation")
    except Exception:
        # The connection may already be closing during shutdown / faults.
        # Swallow defensively — the connection is on its way back to the
        # pool (or being discarded) either way.
        pass
    finally:
        cur.close()


SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session."""
    async with SessionLocal() as session:
        yield session
