"""platform_invites.supabase_user_id — store the invited Supabase auth user id

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: pre-existing invites have no captured id; new invites store the
    # Supabase auth user id returned by invite_user_by_email so revoke can
    # delete that exact user (O(1), no global list_users scan).
    op.execute("ALTER TABLE platform_invites ADD COLUMN supabase_user_id uuid")


def downgrade() -> None:
    op.execute("ALTER TABLE platform_invites DROP COLUMN IF EXISTS supabase_user_id")
