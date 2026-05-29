"""Invite-email outbox (PAR-D H5): enqueue on the request path; claim + send on
the worker.

Request path: ``enqueue_invite_email`` inserts an outbox row in the CALLER's
transaction (the route commits it alongside the invite row) — no Supabase call
inside the open tx.

Worker path: ``process_due_batch`` claims due rows under
``FOR UPDATE SKIP LOCKED`` and bumps ``next_attempt_at`` by a lease, commits
(releasing the row lock), THEN performs the Supabase calls with NO DB tx open —
so a slow Supabase HTTP call can't trip ``idle_in_transaction_session_timeout``
— and finally records success/failure in a fresh short tx. Idempotent-ish:
re-sending an invite email after a crash is harmless (Supabase de-dupes the
invite by email), and the lease prevents two workers double-claiming.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any
from uuid import UUID

import httpx
from gotrue.errors import AuthApiError, AuthRetryableError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from supabase import create_client

from ..core.config import get_settings
from ..core.logging import get_logger

_log = get_logger(__name__)

# Retry budget + backoff. Attempts climb 5,10,20,...,capped; after the cap we
# park the row far in the future (operator can inspect last_error).
_MAX_ATTEMPTS = 8
_BACKOFF_CAP_SEC = 300
# While a claimed row is being processed (Supabase call, no DB tx held), push
# its next_attempt_at out so a second poll/worker won't re-claim it.
_LEASE_SEC = 120

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
# Tables the worker may write supabase_user_id back to (allow-list — the value
# is interpolated into SQL, so it must never come from untrusted input).
_WRITEBACK_TABLES = {"platform_invites"}


async def enqueue_invite_email(
    db: AsyncSession,
    *,
    email: str,
    app_metadata: dict[str, Any],
    writeback: dict[str, str] | None = None,
) -> None:
    """Stage an invite email in the CURRENT transaction (the caller commits).

    ``writeback`` (optional) tells the worker to store the resolved Supabase user
    id back onto an invite row, e.g. ``{"table": "platform_invites", "id": ...}``.
    """
    payload: dict[str, Any] = {"email": email, "app_metadata": app_metadata}
    if writeback is not None:
        payload["writeback"] = writeback
    await db.execute(
        text("INSERT INTO invite_email_outbox (payload) VALUES (CAST(:p AS jsonb))"),
        {"p": json.dumps(payload)},
    )


def _backoff_secs(attempts: int) -> float:
    return float(min(_BACKOFF_CAP_SEC, 5 * (2**attempts)))


async def _claim_due(db: AsyncSession, limit: int) -> list[dict[str, Any]]:
    rows = (
        (
            await db.execute(
                text(
                    "SELECT id, payload, attempts FROM invite_email_outbox "
                    "WHERE succeeded_at IS NULL AND next_attempt_at <= now() "
                    "ORDER BY next_attempt_at FOR UPDATE SKIP LOCKED LIMIT :lim"
                ),
                {"lim": limit},
            )
        )
        .mappings()
        .all()
    )
    if rows:
        await db.execute(
            text(
                "UPDATE invite_email_outbox "
                "SET next_attempt_at = now() + make_interval(secs => :lease) "
                "WHERE id = ANY(:ids)"
            ),
            {"lease": float(_LEASE_SEC), "ids": [r["id"] for r in rows]},
        )
    await db.commit()
    return [dict(r) for r in rows]


async def _send_one(payload: dict[str, Any]) -> str | None:
    """Perform the Supabase calls for one outbox row. Returns the Supabase user
    id (or None). Raises on any Supabase failure (caller records + backs off)."""
    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
    email: str = payload["email"]

    result = await asyncio.wait_for(
        asyncio.to_thread(lambda: sb.auth.admin.invite_user_by_email(email)),
        timeout=cfg.supabase_timeout_sec,
    )
    sb_user_id = getattr(getattr(result, "user", None), "id", None)
    app_metadata: dict[str, Any] = payload.get("app_metadata") or {}
    if isinstance(sb_user_id, str) and app_metadata:
        await asyncio.wait_for(
            asyncio.to_thread(
                lambda: sb.auth.admin.update_user_by_id(sb_user_id, {"app_metadata": app_metadata})
            ),
            timeout=cfg.supabase_timeout_sec,
        )
    return sb_user_id if isinstance(sb_user_id, str) else None


async def _mark_success(
    db: AsyncSession, row_id: UUID, payload: dict[str, Any], sb_user_id: str | None
) -> None:
    writeback = payload.get("writeback")
    if writeback and sb_user_id and writeback.get("table") in _WRITEBACK_TABLES:
        table = writeback["table"]  # allow-listed above; safe to interpolate
        await db.execute(
            text(
                f"UPDATE {table} SET supabase_user_id = CAST(:sid AS uuid) "
                "WHERE id = CAST(:iid AS uuid)"
            ),
            {"sid": sb_user_id, "iid": writeback["id"]},
        )
    await db.execute(
        text(
            "UPDATE invite_email_outbox SET succeeded_at = now(), last_error = NULL WHERE id = :id"
        ),
        {"id": row_id},
    )
    await db.commit()


async def _mark_failure(db: AsyncSession, row_id: UUID, attempts: int, err: str) -> None:
    new_attempts = attempts + 1
    if new_attempts >= _MAX_ATTEMPTS:
        # Exhausted: park far out so it stops polling; last_error stays for ops.
        await db.execute(
            text(
                "UPDATE invite_email_outbox SET attempts = :a, last_error = :e, "
                "next_attempt_at = now() + interval '100 years' WHERE id = :id"
            ),
            {"a": new_attempts, "e": err, "id": row_id},
        )
    else:
        await db.execute(
            text(
                "UPDATE invite_email_outbox SET attempts = :a, last_error = :e, "
                "next_attempt_at = now() + make_interval(secs => :secs) WHERE id = :id"
            ),
            {"a": new_attempts, "e": err, "secs": _backoff_secs(new_attempts), "id": row_id},
        )
    await db.commit()


async def process_due_batch(session_factory: SessionFactory, *, limit: int = 10) -> int:
    """Claim up to ``limit`` due rows and send each. Returns the count sent OK.

    The Supabase calls run with NO DB transaction open (the claim tx is committed
    first); success/failure is recorded in a fresh tx per row."""
    async with session_factory() as db:
        claimed = await _claim_due(db, limit)
    sent = 0
    for row in claimed:
        try:
            sb_user_id = await _send_one(row["payload"])
        except (TimeoutError, AuthApiError, AuthRetryableError, httpx.HTTPError) as e:
            async with session_factory() as db:
                await _mark_failure(db, row["id"], int(row["attempts"]), str(e))
            _log.warning("invite_outbox_send_failed", outbox_id=str(row["id"]), error=str(e))
            continue
        async with session_factory() as db:
            await _mark_success(db, row["id"], row["payload"], sb_user_id)
        sent += 1
    return sent
