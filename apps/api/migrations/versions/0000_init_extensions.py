"""init: enable required Postgres extensions

Revision ID: 0000
Revises:
Create Date: 2026-05-14

Enables Postgres extensions used across the platform. Supabase ships these
binaries pre-installed; this migration is the explicit `CREATE EXTENSION`
declaration so every environment (dev, staging, prod) is guaranteed to have
them with one command (`alembic upgrade head`).

- vector  — pgvector, required by the analysis toolkit embedding cache and
            future RAG/similarity features.
- pgcrypto — gen_random_uuid() used by table defaults.
- citext  — case-insensitive text columns (emails, slugs).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0000"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS citext")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS vector")
