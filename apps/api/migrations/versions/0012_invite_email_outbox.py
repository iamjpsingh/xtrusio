"""Invite-email outbox (PAR-D H5).

Today ``create_platform_invite`` / ``create_tenant_invite`` call Supabase
(``invite_user_by_email`` + ``update_user_by_id``) **inside the request's DB
transaction** and then commit — so a commit failure after a successful Supabase
call leaves a phantom invite email (the user got an email for an invite row that
was rolled back), and a slow Supabase call holds a DB connection + worker.

The outbox makes it transactional: the invite row + an outbox row are inserted
in ONE tx and committed together; a background worker (``core/outbox_worker``)
later claims due rows and performs the Supabase calls OUTSIDE any request tx,
with retry/backoff. No external call inside an open DB tx; no phantom emails.

Backend-only table: RLS enabled with no policy and no grant to ``authenticated``
(the worker uses the owner connection, which bypasses RLS).

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE invite_email_outbox (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            payload         jsonb NOT NULL,
            attempts        int NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            succeeded_at    timestamptz,
            last_error      text,
            created_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # Partial index over the worker's hot query: due, not-yet-succeeded rows.
    op.execute(
        "CREATE INDEX invite_email_outbox_due_idx ON invite_email_outbox (next_attempt_at) "
        "WHERE succeeded_at IS NULL"
    )
    # Backend-only: RLS on, no policy, no authenticated grant. The owner backend
    # connection bypasses RLS; authenticated has no access at all.
    op.execute("ALTER TABLE invite_email_outbox ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS invite_email_outbox")
