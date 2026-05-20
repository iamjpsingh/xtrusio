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
    op.execute("REVOKE EXECUTE ON FUNCTION has_workspace_perm(uuid, uuid, text) FROM public")
    op.execute("GRANT EXECUTE ON FUNCTION has_workspace_perm(uuid, uuid, text) TO authenticated")

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

    # Replace 0006's permissive interim RBAC-table SELECT policies with
    # resolver-gated ones (removes the cross-tenant user_roles over-read the
    # P1 review flagged). Writes still go through the owner backend conn
    # (RLS does not constrain it) — no write policies needed for authenticated.
    op.execute("DROP POLICY IF EXISTS permissions_authenticated_read ON permissions")
    op.execute("DROP POLICY IF EXISTS roles_authenticated_read ON roles")
    op.execute("DROP POLICY IF EXISTS role_permissions_authenticated_read ON role_permissions")
    op.execute("DROP POLICY IF EXISTS user_roles_authenticated_read ON user_roles")
    op.execute("DROP POLICY IF EXISTS rbac_audit_log_no_read ON rbac_audit_log")

    # permissions: the catalog is non-sensitive key metadata; any authenticated
    # user may read it (unchanged from 0006 intent).
    op.execute(
        "CREATE POLICY permissions_read ON permissions " "FOR SELECT TO authenticated USING (true)"
    )
    # roles: visible to whoever may manage roles in that scope/workspace.
    op.execute(
        """
        CREATE POLICY roles_read ON roles
            FOR SELECT TO authenticated
            USING (
                (scope = 'platform'
                    AND has_platform_perm(auth.uid(), 'platform.roles.manage'))
             OR (scope = 'workspace'
                    AND has_workspace_perm(auth.uid(), workspace_id, 'workspace.roles.manage'))
            )
        """
    )
    # role_permissions: gated via can_manage_role (SECURITY DEFINER → no
    # roles-RLS recursion in the subquery).
    op.execute(
        "CREATE POLICY role_permissions_read ON role_permissions "
        "FOR SELECT TO authenticated USING (can_manage_role(auth.uid(), role_id))"
    )
    # user_roles: a user always sees their OWN grants; RBAC managers see grants
    # in the scope/workspace they manage. (No blanket read.)
    op.execute(
        """
        CREATE POLICY user_roles_read ON user_roles
            FOR SELECT TO authenticated
            USING (
                auth_user_id = auth.uid()
             OR (workspace_id IS NULL
                    AND has_platform_perm(auth.uid(), 'platform.roles.manage'))
             OR (workspace_id IS NOT NULL
                    AND has_workspace_perm(auth.uid(), workspace_id, 'workspace.roles.manage'))
            )
        """
    )
    # rbac_audit_log: scope-appropriate audit-read permission.
    op.execute(
        """
        CREATE POLICY rbac_audit_log_read ON rbac_audit_log
            FOR SELECT TO authenticated
            USING (
                (scope = 'platform'
                    AND has_platform_perm(auth.uid(), 'platform.audit.read'))
             OR (scope = 'workspace'
                    AND has_workspace_perm(auth.uid(), workspace_id, 'workspace.audit.read'))
            )
        """
    )


def downgrade() -> None:
    # Policy/helper restoration: Tasks 2 & 3 add ABOVE the function drops.
    # Restore 0006's interim RBAC-table policies verbatim.
    op.execute("DROP POLICY IF EXISTS rbac_audit_log_read ON rbac_audit_log")
    op.execute("DROP POLICY IF EXISTS user_roles_read ON user_roles")
    op.execute("DROP POLICY IF EXISTS role_permissions_read ON role_permissions")
    op.execute("DROP POLICY IF EXISTS roles_read ON roles")
    op.execute("DROP POLICY IF EXISTS permissions_read ON permissions")
    op.execute(
        "CREATE POLICY permissions_authenticated_read ON permissions "
        "FOR SELECT TO authenticated USING (true)"
    )
    op.execute(
        "CREATE POLICY roles_authenticated_read ON roles "
        "FOR SELECT TO authenticated USING (true)"
    )
    op.execute(
        "CREATE POLICY role_permissions_authenticated_read ON role_permissions "
        "FOR SELECT TO authenticated USING (true)"
    )
    op.execute(
        "CREATE POLICY user_roles_authenticated_read ON user_roles "
        "FOR SELECT TO authenticated USING (true)"
    )
    op.execute(
        "CREATE POLICY rbac_audit_log_no_read ON rbac_audit_log "
        "FOR SELECT TO authenticated USING (false)"
    )

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
