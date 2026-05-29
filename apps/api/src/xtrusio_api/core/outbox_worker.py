"""In-process invite-email outbox worker (PAR-D H5).

Launched from the FastAPI lifespan as an ``asyncio`` task. Polls the
``invite_email_outbox`` every ``OUTBOX_POLL_SEC`` and sends due invite emails via
``services.invite_outbox.process_due_batch`` (which performs the Supabase calls
with no DB tx held). A single in-process worker is enough for launch; the
``FOR UPDATE SKIP LOCKED`` claim in ``process_due_batch`` keeps it correct if it
ever becomes multi-process.

The worker is resilient: any iteration error is logged and the loop continues.
Shutdown is cooperative via an ``asyncio.Event`` set in the lifespan's finally.
"""

from __future__ import annotations

import asyncio
import contextlib

from .config import get_settings
from .logging import get_logger

_log = get_logger(__name__)


async def run_outbox_worker(stop: asyncio.Event) -> None:
    # Local import avoids a core -> services import edge at module load.
    from ..services.invite_outbox import process_due_batch
    from .db import SessionLocal

    interval = float(get_settings().outbox_poll_sec)
    _log.info("outbox_worker_started", poll_sec=interval)
    while not stop.is_set():
        try:
            sent = await process_due_batch(SessionLocal)
            if sent:
                _log.info("outbox_worker_sent", count=sent)
        except Exception:
            # Never let a transient error kill the loop.
            _log.exception("outbox_worker_iteration_failed")
        # Sleep until the next poll OR an early wakeup on shutdown.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
    _log.info("outbox_worker_stopped")
