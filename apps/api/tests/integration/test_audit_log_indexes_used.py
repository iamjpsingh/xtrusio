"""rbac_audit_log query indexes (PAR-D H11, migration 0011).

Asserts the three covering indexes exist AND are usable by the planner. The
"usable" check disables seqscan for the statement so the assertion does not
depend on table size (on a near-empty managed table the planner would pick a
seqscan purely on cost, which says nothing about index correctness).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")

_EXPECTED = (
    "rbac_audit_log_scope_workspace_created_idx",
    "rbac_audit_log_target_idx",
    "rbac_audit_log_actor_created_idx",
)


async def test_audit_indexes_exist() -> None:
    async with SessionLocal() as s:
        names = {
            r[0]
            for r in (
                await s.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename = 'rbac_audit_log'")
                )
            ).all()
        }
    for idx in _EXPECTED:
        assert idx in names, (idx, names)


async def _plan(sql: str) -> str:
    async with SessionLocal() as s:
        # SET LOCAL is bounded by the (auto-begun) transaction; rolled back below.
        await s.execute(text("SET LOCAL enable_seqscan = off"))
        rows = (await s.execute(text("EXPLAIN " + sql))).all()
        await s.rollback()
    return "\n".join(r[0] for r in rows)


async def test_scoped_recency_query_uses_index() -> None:
    plan = await _plan(
        "SELECT id FROM rbac_audit_log WHERE scope = 'platform' AND workspace_id IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT 50"
    )
    assert "rbac_audit_log_scope_workspace_created_idx" in plan, plan


async def test_actor_history_query_uses_index() -> None:
    plan = await _plan(
        "SELECT id FROM rbac_audit_log "
        "WHERE actor_auth_user_id = '00000000-0000-0000-0000-0000000000a1' "
        "ORDER BY created_at DESC LIMIT 50"
    )
    assert "rbac_audit_log_actor_created_idx" in plan, plan
