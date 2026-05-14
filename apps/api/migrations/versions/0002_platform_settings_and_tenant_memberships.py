"""platform_settings singleton + tenant_role enum + tenant_memberships

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-14

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE tenant_role AS ENUM ('owner', 'admin', 'editor', 'read_only')")

    # platform_settings — singleton row enforced via CHECK (id=1).
    op.execute(
        """
        CREATE TABLE platform_settings (
            id              smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            signups_enabled boolean NOT NULL DEFAULT false,
            updated_at      timestamptz NOT NULL DEFAULT now(),
            updated_by      uuid REFERENCES auth.users(id) ON DELETE SET NULL
        )
        """
    )
    op.execute("INSERT INTO platform_settings (id, signups_enabled) VALUES (1, false)")

    # tenant_memberships
    op.execute(
        """
        CREATE TABLE tenant_memberships (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            role       tenant_role NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX tenant_memberships_user_id_idx ON tenant_memberships(user_id)"
    )
    op.execute(
        "CREATE INDEX tenant_memberships_tenant_id_idx ON tenant_memberships(tenant_id)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX tenant_memberships_one_owner_per_tenant
            ON tenant_memberships(tenant_id)
            WHERE role = 'owner'
        """
    )

    op.execute(
        "CREATE TRIGGER tenant_memberships_set_updated_at "
        "BEFORE UPDATE ON tenant_memberships "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # RLS — platform_settings
    op.execute("ALTER TABLE platform_settings ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY platform_settings_authenticated_read ON platform_settings
            FOR SELECT TO authenticated USING (true)
        """
    )
    op.execute(
        """
        CREATE POLICY platform_settings_super_admin_write ON platform_settings
            FOR UPDATE TO authenticated
            USING (EXISTS (
                SELECT 1 FROM platform_users pu
                WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
            ))
            WITH CHECK (EXISTS (
                SELECT 1 FROM platform_users pu
                WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
            ))
        """
    )

    # RLS — tenant_memberships
    op.execute("ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_memberships_self_read ON tenant_memberships
            FOR SELECT TO authenticated USING (user_id = auth.uid())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_memberships_super_admin_all ON tenant_memberships
            FOR ALL TO authenticated
            USING (EXISTS (
                SELECT 1 FROM platform_users pu
                WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
            ))
            WITH CHECK (EXISTS (
                SELECT 1 FROM platform_users pu
                WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
            ))
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_memberships_owner_admin_manage ON tenant_memberships
            FOR ALL TO authenticated
            USING (EXISTS (
                SELECT 1 FROM tenant_memberships m
                WHERE m.tenant_id = tenant_memberships.tenant_id
                  AND m.user_id = auth.uid()
                  AND m.role IN ('owner','admin')
            ))
            WITH CHECK (EXISTS (
                SELECT 1 FROM tenant_memberships m
                WHERE m.tenant_id = tenant_memberships.tenant_id
                  AND m.user_id = auth.uid()
                  AND m.role IN ('owner','admin')
            ))
        """
    )

    # tenants — add tenant_member read policy (super_admin policy from 0001 keeps FOR ALL).
    op.execute(
        """
        CREATE POLICY tenants_member_read ON tenants
            FOR SELECT TO authenticated
            USING (EXISTS (
                SELECT 1 FROM tenant_memberships m
                WHERE m.tenant_id = tenants.id AND m.user_id = auth.uid()
            ))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenants_member_read ON tenants")
    op.execute("DROP TABLE IF EXISTS tenant_memberships")
    op.execute("DROP TABLE IF EXISTS platform_settings")
    op.execute("DROP TYPE IF EXISTS tenant_role")
