"""GET /api/platform/job-runs — worker/system job-run log viewer.

Gated by ``platform.audit.read`` (the same operator audience as the audit log —
both seeded platform system roles hold it). Shows one row per background-worker
batch that did work: what ran, when, duration, item counts, and outcome.

A dedicated ``platform.system.read`` permission could split this from the audit
gate later; reusing ``platform.audit.read`` keeps this slice free of a
permission-catalog reconcile dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from ..core.permissions import require_permission
from ..schemas.job_runs import JobRunOut, JobRunsPage
from ..services.job_runs import _decode_job_cursor, list_job_runs

router = APIRouter(prefix="/api/platform/job-runs", tags=["platform-job-runs"])


@router.get("", response_model=JobRunsPage)
async def list_events(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    job_name: Annotated[str | None, Query()] = None,
) -> JobRunsPage:
    await require_permission(db, user.user_id, "platform.audit.read")
    effective_limit = limit if limit > 0 else DEFAULT_LIMIT
    decoded: tuple[datetime, int] | None = None
    if cursor is not None:
        try:
            decoded = _decode_job_cursor(cursor)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_job_runs(
        db, cursor=decoded, limit=effective_limit, job_name=job_name
    )
    return JobRunsPage(
        items=[JobRunOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
