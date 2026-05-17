"""RLS permission engine: has_platform_perm/has_workspace_perm resolvers,
delegate the 0003 enum helpers, perm-aware RBAC-table policies.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-17

Spec: docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md §5/§6.
Pure raw SQL. Resolvers are SECURITY DEFINER (bypass RLS internally — no
recursion, the 0003 technique) and are the single source of truth both RLS
and the P3 backend call.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION has_platform_perm(uid uuid, perm_key text)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                            AND r.scope = 'platform'
                            AND r.workspace_id IS NULL
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.auth_user_id = uid
                  AND ur.workspace_id IS NULL
                  AND p.scope = 'platform'
                  AND p.key = perm_key
                  AND NOT p.is_deprecated
            )
        $$
        """
    )
    op.execute("REVOKE EXECUTE ON FUNCTION has_platform_perm(uuid, text) FROM public")
    op.execute("GRANT EXECUTE ON FUNCTION has_platform_perm(uuid, text) TO authenticated")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION has_workspace_perm(uid uuid, tid uuid, perm_key text)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                            AND r.scope = 'workspace'
                            AND r.workspace_id = tid
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.auth_user_id = uid
                  AND ur.workspace_id = tid
                  AND p.scope = 'workspace'
                  AND p.key = perm_key
                  AND NOT p.is_deprecated
            )
        $$
        """
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION has_workspace_perm(uuid, uuid, text) FROM public"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION has_workspace_perm(uuid, uuid, text) TO authenticated"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION can_manage_role(uid uuid, rid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM roles r
                WHERE r.id = rid
                  AND (
                    (r.scope = 'platform'
                       AND has_platform_perm(uid, 'platform.roles.manage'))
                 OR (r.scope = 'workspace'
                       AND has_workspace_perm(uid, r.workspace_id, 'workspace.roles.manage'))
                  )
            )
        $$
        """
    )
    op.execute("REVOKE EXECUTE ON FUNCTION can_manage_role(uuid, uuid) FROM public")
    op.execute("GRANT EXECUTE ON FUNCTION can_manage_role(uuid, uuid) TO authenticated")

    # Supersede the 0003 enum helpers with TRANSITION-SAFE bodies: the new
    # resolver OR the original 0003 enum check. Same signatures → every
    # existing 0003/0004 policy keeps working unchanged. The OR-legacy
    # disjunct is mandatory (spec §5, corrected): pure delegation strands
    # enum-era memberships until P3 (proven: 0006 passes, pure-0007 fails) and
    # would lock newly-onboarded owners out — this superset breaks nothing
    # mid-flight (§7.5) while giving instant-revoke for RBAC-granted access.
    # SECURITY DEFINER → the legacy EXISTS subqueries don't recurse (0003
    # technique). P3 retires the legacy disjunct when user_roles is authoritative.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_super_admin(uid uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT has_platform_perm(uid, 'platform.roles.manage')
                OR EXISTS (
                    SELECT 1 FROM platform_users
                    WHERE id = uid AND role = 'super_admin' AND is_active
                )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_owner_or_admin(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT has_workspace_perm(uid, tid, 'workspace.members.manage')
                OR EXISTS (
                    SELECT 1 FROM tenant_memberships
                    WHERE user_id = uid AND tenant_id = tid
                      AND role IN ('owner','admin')
                )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_member(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                    SELECT 1 FROM user_roles
                    WHERE auth_user_id = uid AND workspace_id = tid
                )
                OR EXISTS (
                    SELECT 1 FROM tenant_memberships
                    WHERE user_id = uid AND tenant_id = tid
                )
        $$
        """
    )

    # Policies: Task 3 adds BELOW THIS LINE (same upgrade()).


def downgrade() -> None:
    # Policy/helper restoration: Tasks 2 & 3 add ABOVE the function drops.
    # Restore the original 0003 enum-reading helper bodies.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_super_admin(uid uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM platform_users
                WHERE id = uid AND role = 'super_admin' AND is_active
            )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_owner_or_admin(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM tenant_memberships
                WHERE user_id = uid AND tenant_id = tid AND role IN ('owner','admin')
            )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_member(uid uuid, tid uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM tenant_memberships
                WHERE user_id = uid AND tenant_id = tid
            )
        $$
        """
    )
    op.execute("DROP FUNCTION IF EXISTS can_manage_role(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS has_workspace_perm(uuid, uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS has_platform_perm(uuid, text)")
