"""Fix infinite recursion in super_admin RLS + grant DML to authenticated.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-14

The `platform_users_super_admin_all` policy from 0001 was FOR ALL with a
USING clause that SELECT'd from platform_users — causing infinite recursion
when any non-postgres role queried the table. The same EXISTS pattern in
later super_admin policies (tenants, platform_settings, tenant_memberships)
inherited the bug transitively. The `tenant_memberships_owner_admin_manage`
policy (0002) self-references tenant_memberships and is FOR ALL, so plain
SELECT against tenant_memberships — or any table whose policy transitively
queries tenant_memberships, such as tenants_member_read — also recurses.

Fix: introduce SECURITY DEFINER helpers that perform the lookups with the
function-owner's privileges (postgres), bypassing RLS — the standard Supabase
RLS-helper pattern. `is_super_admin(uid)` replaces the four super_admin
EXISTS clauses; `is_tenant_owner_or_admin(uid, tenant_id)` and
`is_tenant_member(uid, tenant_id)` replace the recursive
tenant_memberships / tenants_member_read clauses.

Also: GRANT SELECT/INSERT/UPDATE/DELETE on platform_users, platform_settings,
tenants, tenant_memberships to the `authenticated` role. Alembic-created
tables don't inherit Supabase's auto-grants, so without this the policies
are unreachable from authenticated-role queries.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SECURITY DEFINER helper bypasses RLS during the lookup.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_super_admin(uid uuid) RETURNS boolean
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM platform_users
                WHERE id = uid AND role = 'super_admin' AND is_active
            )
        $$
        """
    )
    op.execute("REVOKE EXECUTE ON FUNCTION is_super_admin(uuid) FROM public")
    op.execute("GRANT EXECUTE ON FUNCTION is_super_admin(uuid) TO authenticated")

    # Tenant-membership helpers — same pattern, used to break the
    # tenant_memberships self-recursion and the tenants -> tenant_memberships
    # transitive recursion.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_owner_or_admin(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM tenant_memberships
                WHERE user_id = uid AND tenant_id = tid AND role IN ('owner','admin')
            )
        $$
        """
    )
    op.execute("REVOKE EXECUTE ON FUNCTION is_tenant_owner_or_admin(uuid, uuid) FROM public")
    op.execute(
        "GRANT EXECUTE ON FUNCTION is_tenant_owner_or_admin(uuid, uuid) TO authenticated"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_member(uid uuid, tid uuid) RETURNS boolean
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM tenant_memberships
                WHERE user_id = uid AND tenant_id = tid
            )
        $$
        """
    )
    op.execute("REVOKE EXECUTE ON FUNCTION is_tenant_member(uuid, uuid) FROM public")
    op.execute("GRANT EXECUTE ON FUNCTION is_tenant_member(uuid, uuid) TO authenticated")

    # Rewrite recursive policies. ALTER POLICY ... USING/WITH CHECK is
    # supported since Postgres 9.6.
    op.execute(
        """
        ALTER POLICY platform_users_super_admin_all ON platform_users
            USING (is_super_admin(auth.uid()))
            WITH CHECK (is_super_admin(auth.uid()))
        """
    )
    op.execute(
        """
        ALTER POLICY tenants_super_admin_all ON tenants
            USING (is_super_admin(auth.uid()))
            WITH CHECK (is_super_admin(auth.uid()))
        """
    )
    op.execute(
        """
        ALTER POLICY platform_settings_super_admin_write ON platform_settings
            USING (is_super_admin(auth.uid()))
            WITH CHECK (is_super_admin(auth.uid()))
        """
    )
    op.execute(
        """
        ALTER POLICY tenant_memberships_super_admin_all ON tenant_memberships
            USING (is_super_admin(auth.uid()))
            WITH CHECK (is_super_admin(auth.uid()))
        """
    )
    op.execute(
        """
        ALTER POLICY tenant_memberships_owner_admin_manage ON tenant_memberships
            USING (is_tenant_owner_or_admin(auth.uid(), tenant_id))
            WITH CHECK (is_tenant_owner_or_admin(auth.uid(), tenant_id))
        """
    )
    op.execute(
        """
        ALTER POLICY tenants_member_read ON tenants
            USING (is_tenant_member(auth.uid(), id))
        """
    )

    # Grant DML on the four migration-created tables to the authenticated
    # role. RLS still enforces row visibility; these grants just let the
    # role attempt the query (without them Postgres aborts with
    # "permission denied for table" before checking RLS).
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            platform_users, platform_settings, tenants, tenant_memberships
            TO authenticated
        """
    )


def downgrade() -> None:
    op.execute(
        """
        REVOKE SELECT, INSERT, UPDATE, DELETE ON
            platform_users, platform_settings, tenants, tenant_memberships
            FROM authenticated
        """
    )

    # Restore the original (recursive) policies from 0001 / 0002.
    op.execute(
        """
        ALTER POLICY platform_users_super_admin_all ON platform_users
            USING (EXISTS (
                SELECT 1 FROM platform_users pu2
                WHERE pu2.id = auth.uid() AND pu2.role = 'super_admin' AND pu2.is_active
            ))
            WITH CHECK (EXISTS (
                SELECT 1 FROM platform_users pu2
                WHERE pu2.id = auth.uid() AND pu2.role = 'super_admin' AND pu2.is_active
            ))
        """
    )
    op.execute(
        """
        ALTER POLICY tenants_super_admin_all ON tenants
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
        ALTER POLICY platform_settings_super_admin_write ON platform_settings
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
        ALTER POLICY tenant_memberships_super_admin_all ON tenant_memberships
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
        ALTER POLICY tenant_memberships_owner_admin_manage ON tenant_memberships
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
    op.execute(
        """
        ALTER POLICY tenants_member_read ON tenants
            USING (EXISTS (
                SELECT 1 FROM tenant_memberships m
                WHERE m.tenant_id = tenants.id AND m.user_id = auth.uid()
            ))
        """
    )

    op.execute("DROP FUNCTION IF EXISTS is_tenant_member(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS is_tenant_owner_or_admin(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS is_super_admin(uuid)")
