"""Pydantic schemas for the worker/system job-run log viewer.

Mirrors the ``job_runs`` table (migration 0014). ``id`` is a ``bigint`` and the
table records one row per worker batch that did work.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_name: str
    status: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    items_processed: int
    items_succeeded: int
    items_failed: int
    detail: dict[str, Any] | None
    created_at: datetime


class JobRunsPage(BaseModel):
    items: list[JobRunOut]
    next_cursor: str | None = None
