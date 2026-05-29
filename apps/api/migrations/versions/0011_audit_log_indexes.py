"""Audit-log query indexes (PAR-D H11).

`rbac_audit_log` had only its PK, so every list query (the platform/workspace
audit viewers, paginated by ``created_at DESC, id DESC`` and filtered by scope /
workspace / actor / target) was a full scan + sort. Three covering indexes:

  - (scope, workspace_id, created_at DESC) — the scoped list-by-recency path.
  - (target_type, target_id)               — "history for this object".
  - (actor_auth_user_id, created_at DESC)   — "what did this actor do".

Built ``CONCURRENTLY`` (via Alembic's ``autocommit_block``) so creating them on a
populated table does not take an ACCESS EXCLUSIVE lock — this is the production-
migration pattern (audit M21) for any future index add. ``IF NOT EXISTS`` keeps
the migration re-runnable after a partial/failed concurrent build.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "rbac_audit_log_scope_workspace_created_idx",
        "rbac_audit_log (scope, workspace_id, created_at DESC)",
    ),
    (
        "rbac_audit_log_target_idx",
        "rbac_audit_log (target_type, target_id)",
    ),
    (
        "rbac_audit_log_actor_created_idx",
        "rbac_audit_log (actor_auth_user_id, created_at DESC)",
    ),
)


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction; autocommit_block commits the
    # migration's tx, runs each statement in autocommit, then reopens.
    with op.get_context().autocommit_block():
        for name, target in _INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {target}")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _ in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
