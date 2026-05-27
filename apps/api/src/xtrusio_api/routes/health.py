"""Health probes — liveness vs readiness (PAR-B L1).

``GET /health/live`` is the K8s-shaped liveness probe: returns 200 if the
process answered. No auth, no DB. Cheap.

``GET /health/ready`` is the readiness probe: returns 200 only if the app's
DB pool can execute ``SELECT 1`` within a tight timeout. Returns 503
``not_ready`` on failure — operators / orchestrators pull the pod out of
rotation when this flips red.

``GET /health`` is kept as an alias of ``/health/live`` so the existing
contract callers do not break.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Liveness — process answered. No dependencies."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str]:
    """Readiness — DB pool can answer within 2 seconds."""
    try:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2.0)
    except (TimeoutError, Exception) as e:
        # Any failure flips us out of rotation — the orchestrator decides
        # whether to restart based on liveness; readiness only stops traffic.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"not_ready: {type(e).__name__}",
        ) from e
    return {"status": "ok"}


@router.get("/health")
async def health() -> dict[str, str]:
    """Backward-compat alias of ``/health/live`` for existing pingers."""
    return {"status": "ok"}
