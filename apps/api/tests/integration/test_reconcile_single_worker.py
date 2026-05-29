"""Boot-reconcile advisory lock (PAR-D M9).

The lifespan gates ``reconcile_rbac`` / ``reconcile_user_roles_from_enums``
behind ``pg_try_advisory_lock(0x52424143)`` held on a dedicated connection, so
when N workers boot together only the lock-holder runs the (idempotent but
expensive) reconcile and the rest skip. This verifies the lock primitive the
lifespan relies on: a second session cannot acquire the same key while the first
holds it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")

_RECONCILE_LOCK_KEY = 0x52424143


async def test_second_worker_cannot_acquire_reconcile_lock() -> None:
    async with SessionLocal() as holder:
        got = (
            await holder.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": _RECONCILE_LOCK_KEY}
            )
        ).scalar_one()
        assert got is True, "first worker must acquire the reconcile lock"
        try:
            async with SessionLocal() as other:
                got_other = (
                    await other.execute(
                        text("SELECT pg_try_advisory_lock(:k)"), {"k": _RECONCILE_LOCK_KEY}
                    )
                ).scalar_one()
            assert (
                got_other is False
            ), "second worker must NOT acquire the held lock (skips reconcile)"
        finally:
            await holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _RECONCILE_LOCK_KEY})


async def test_lock_reacquirable_after_release() -> None:
    async with SessionLocal() as s:
        assert (
            await s.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _RECONCILE_LOCK_KEY})
        ).scalar_one() is True
        await s.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _RECONCILE_LOCK_KEY})
    # A fresh session can take it again once released.
    async with SessionLocal() as s2:
        assert (
            await s2.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _RECONCILE_LOCK_KEY})
        ).scalar_one() is True
        await s2.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _RECONCILE_LOCK_KEY})
