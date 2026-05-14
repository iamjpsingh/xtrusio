"""init: tenants + platform_users + platform_role enum

Revision ID: 0001
Revises:
Create Date: 2026-05-08

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = "0000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE platform_role AS ENUM ('super_admin', 'admin', 'editor')")

    op.execute(
        """
        CREATE TABLE tenants (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            slug        citext NOT NULL UNIQUE,
            name        text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            created_by  uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
            CONSTRAINT tenants_slug_format
                CHECK (slug ~ '^[a-z][a-z0-9-]{1,62}[a-z0-9]$')
        )
        """
    )
    op.execute("CREATE INDEX tenants_created_by_idx ON tenants(created_by)")

    op.execute(
        """
        CREATE TABLE platform_users (
            id                uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
            email             citext NOT NULL UNIQUE,
            role              platform_role NOT NULL,
            is_active         boolean NOT NULL DEFAULT true,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            last_sign_in_at   timestamptz
        )
        """
    )
    op.execute("CREATE INDEX platform_users_role_idx ON platform_users(role)")

    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenants_super_admin_all ON tenants
            FOR ALL
            TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM platform_users pu
                    WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM platform_users pu
                    WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
                )
            )
        """
    )

    op.execute("ALTER TABLE platform_users ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY platform_users_self_select ON platform_users
            FOR SELECT
            TO authenticated
            USING (id = auth.uid())
        """
    )
    op.execute(
        """
        CREATE POLICY platform_users_super_admin_all ON platform_users
            FOR ALL
            TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM platform_users pu2
                    WHERE pu2.id = auth.uid() AND pu2.role = 'super_admin' AND pu2.is_active
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM platform_users pu2
                    WHERE pu2.id = auth.uid() AND pu2.role = 'super_admin' AND pu2.is_active
                )
            )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER tenants_set_updated_at BEFORE UPDATE ON tenants "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER platform_users_set_updated_at BEFORE UPDATE ON platform_users "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    # tenants must be dropped first because its RLS policy references platform_users.
    # Triggers are dropped automatically when tables drop.
    op.execute("DROP TABLE IF EXISTS tenants")
    op.execute("DROP TABLE IF EXISTS platform_users")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP TYPE IF EXISTS platform_role")
