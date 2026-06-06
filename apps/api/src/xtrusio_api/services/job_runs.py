"""Worker/system job-run log: writer + cursor-paginated reader.

``record_job_run`` inserts one row describing a completed worker batch (caller
owns the surrounding tx — it does NOT commit). ``list_job_runs`` is the
operator-facing reader, cursor-paginated newest-first.

Cursor format mirrors ``services.platform_audit_log`` (``job_runs.id`` is a
``bigint``, like ``rbac_audit_log.id``): a base64url ``{started_at, id}`` token
ordered by ``(started_at, id) DESC``.

Valid ``status`` values written by the workers: ``success`` (all items ok),
``partial`` (some ok, some failed), ``error`` (all failed).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _encode_job_cursor(started_at: datetime, row_id: int) -> str:
    raw = json.dumps({"t": started_at.isoformat(), "i": row_id}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_job_cursor(token: str) -> tuple[datetime, int]:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        obj = json.loads(raw)
        return datetime.fromisoformat(obj["t"]), int(obj["i"])
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError("invalid cursor") from e


async def record_job_run(
    db: AsyncSession,
    *,
    job_name: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int,
    items_processed: int,
    items_succeeded: int,
    items_failed: int,
    detail: dict[str, Any] | None = None,
) -> None:
    """Insert one job_runs row. Caller owns the surrounding transaction."""
    await db.execute(
        text(
            "INSERT INTO job_runs "
            "(job_name, status, started_at, finished_at, duration_ms, "
            " items_processed, items_succeeded, items_failed, detail) "
            "VALUES (:jn, :st, :sa, :fa, :dm, :ip, :is_, :if_, CAST(:d AS jsonb))"
        ),
        {
            "jn": job_name,
            "st": status,
            "sa": started_at,
            "fa": finished_at,
            "dm": duration_ms,
            "ip": items_processed,
            "is_": items_succeeded,
            "if_": items_failed,
            "d": json.dumps(detail, default=str) if detail is not None else None,
        },
    )


async def list_job_runs(
    db: AsyncSession,
    *,
    cursor: tuple[datetime, int] | None = None,
    limit: int = 50,
    job_name: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Paginated SELECT on ``job_runs``, newest first (started_at DESC, id DESC).

    ``job_name`` (optional) scopes to a single worker. The cursor encodes the
    last returned row's ``(started_at, id)`` and ANDs with the optional
    job_name filter so pagination is unaffected by the filter.
    """
    base = (
        "SELECT id, job_name, status, started_at, finished_at, duration_ms, "
        "items_processed, items_succeeded, items_failed, detail, created_at "
        "FROM job_runs WHERE TRUE "
    )
    params: dict[str, Any] = {"lim": limit + 1}
    name_sql = ""
    if job_name is not None:
        name_sql = "AND job_name = :jn "
        params["jn"] = job_name
    if cursor is not None:
        ts, rid = cursor
        params["ts"] = ts
        params["rid"] = rid
        sql = (
            base
            + name_sql
            + "AND (started_at, id) < (:ts, :rid) ORDER BY started_at DESC, id DESC LIMIT :lim"
        )
    else:
        sql = base + name_sql + "ORDER BY started_at DESC, id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_job_cursor(last["started_at"], int(last["id"]))
        rows = rows[:limit]
    return rows, next_cursor
