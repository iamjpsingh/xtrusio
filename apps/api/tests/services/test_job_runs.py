"""Service-layer tests for the worker/system job-run log.

`job_runs` has no FK and no actor, so these tests seed rows directly via
`record_job_run` and clean them up by their unique `job_name` (the
session-scoped auth.users purge does not touch this table).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.services.job_runs import (
    _decode_job_cursor,
    _encode_job_cursor,
    list_job_runs,
    record_job_run,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

_BASE = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)


async def _cleanup(db: AsyncSession, job_name: str) -> None:
    await db.execute(text("DELETE FROM job_runs WHERE job_name = :jn"), {"jn": job_name})
    await db.commit()


async def _seed(db: AsyncSession, job_name: str, *, n: int, status: str = "success") -> None:
    for i in range(n):
        started = _BASE + timedelta(minutes=i)
        await record_job_run(
            db,
            job_name=job_name,
            status=status,
            started_at=started,
            finished_at=started + timedelta(seconds=1),
            duration_ms=1000,
            items_processed=3,
            items_succeeded=3 if status == "success" else 1,
            items_failed=0 if status == "success" else 2,
            detail=None if status == "success" else {"errors": ["boom"]},
        )
    await db.commit()


async def test_records_and_lists_newest_first(db_session: AsyncSession) -> None:
    jn = f"test_jobrun_{uuid4().hex}"
    try:
        await _seed(db_session, jn, n=3)
        rows, cursor = await list_job_runs(db_session, job_name=jn, limit=50)
        assert [r["job_name"] for r in rows] == [jn, jn, jn]
        # Newest first: started_at descending.
        starts = [r["started_at"] for r in rows]
        assert starts == sorted(starts, reverse=True)
        assert cursor is None
        assert rows[0]["items_processed"] == 3
    finally:
        await _cleanup(db_session, jn)


async def test_partial_status_carries_error_detail(db_session: AsyncSession) -> None:
    jn = f"test_jobrun_{uuid4().hex}"
    try:
        await _seed(db_session, jn, n=1, status="partial")
        rows, _ = await list_job_runs(db_session, job_name=jn, limit=50)
        assert rows[0]["status"] == "partial"
        assert rows[0]["items_failed"] == 2
        assert rows[0]["detail"] == {"errors": ["boom"]}
    finally:
        await _cleanup(db_session, jn)


async def test_cursor_paginates(db_session: AsyncSession) -> None:
    jn = f"test_jobrun_{uuid4().hex}"
    try:
        await _seed(db_session, jn, n=3)
        page1, cursor = await list_job_runs(db_session, job_name=jn, limit=2)
        assert len(page1) == 2
        assert cursor is not None
        decoded = _decode_job_cursor(cursor)
        page2, cursor2 = await list_job_runs(db_session, job_name=jn, cursor=decoded, limit=2)
        assert len(page2) == 1
        assert cursor2 is None
        # No overlap across pages.
        ids = {r["id"] for r in page1} | {r["id"] for r in page2}
        assert len(ids) == 3
    finally:
        await _cleanup(db_session, jn)


async def test_job_name_filter_excludes_others(db_session: AsyncSession) -> None:
    jn_a = f"test_jobrun_{uuid4().hex}"
    jn_b = f"test_jobrun_{uuid4().hex}"
    try:
        await _seed(db_session, jn_a, n=2)
        await _seed(db_session, jn_b, n=2)
        rows, _ = await list_job_runs(db_session, job_name=jn_a, limit=50)
        assert {r["job_name"] for r in rows} == {jn_a}
        assert len(rows) == 2
    finally:
        await _cleanup(db_session, jn_a)
        await _cleanup(db_session, jn_b)


async def test_cursor_roundtrip_and_invalid() -> None:
    token = _encode_job_cursor(_BASE, 42)
    ts, rid = _decode_job_cursor(token)
    assert ts == _BASE
    assert rid == 42
    with pytest.raises(ValueError):
        _decode_job_cursor("not-a-cursor")
