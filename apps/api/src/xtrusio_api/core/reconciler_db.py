"""Separate async engine bound to the least-privileged ``xtrusio_reconciler``
role (PAR-C M15).

The boot/CLI reconciler runs on a DEDICATED least-privileged role so the request
path (``postgres``) cannot effect the bypass on the privilege-escalation guard —
the 0013 ``enforce_priv_escalation`` trigger gates that bypass on
``current_user = 'xtrusio_reconciler'``. (The 0009 system-role immutability
triggers and the 0010 owner-floor still honour the bypass GUC from any role by
design; role-gating those is deferred — see migration 0013's docstring.)

When ``RECONCILE_DATABASE_URL`` is unset (e.g. local dev before the operator
provisions the role) :func:`get_reconciler_sessionmaker` returns ``None`` and
callers fall back to the request engine — the reconciler still runs, but the
bypass rides the request role. Production MUST set the DSN; a warning is logged
at boot when it falls back (see ``main.py``).

The engine is built lazily on first use so importing this module never opens a
connection (matters for tests / CLI paths that don't reconcile).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings
from .db import _engine_kwargs_for

_settings = get_settings()

_reconciler_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_built = False


def get_reconciler_sessionmaker() -> async_sessionmaker[AsyncSession] | None:
    """Return a sessionmaker bound to the reconciler role, or ``None`` when
    ``RECONCILE_DATABASE_URL`` is unset (caller falls back to the request
    engine)."""
    global _reconciler_sessionmaker, _built
    if _settings.reconcile_database_url is None:
        return None
    if not _built:
        url = _settings.reconcile_database_url
        reconciler_engine = create_async_engine(url, **_engine_kwargs_for(url))

        @event.listens_for(reconciler_engine.sync_engine, "connect")
        def _set_reconciler_session_settings(dbapi_conn: Any, _record: Any) -> None:
            # Mirror db.py's post-connect SETs (Supavisor ignores connect-time
            # server_settings); tag the connection so it's distinguishable in
            # pg_stat_activity from request traffic.
            cur = dbapi_conn.cursor()
            try:
                cur.execute(f"SET statement_timeout = {_settings.db_statement_timeout_ms}")
                cur.execute(
                    f"SET idle_in_transaction_session_timeout = "
                    f"{_settings.db_idle_in_tx_timeout_ms}"
                )
                cur.execute("SET application_name = 'xtrusio-reconciler'")
            finally:
                cur.close()

        _reconciler_sessionmaker = async_sessionmaker(
            reconciler_engine, expire_on_commit=False, class_=AsyncSession
        )
        _built = True
    return _reconciler_sessionmaker
