"""RBAC integrity hardening (PAR-C slice 1): search_path, super_admin pin,
workspace-owner floor trigger, tenant_memberships per-action RLS.

Closes audit findings:
  - M17: ``set_updated_at()`` had no ``SET search_path`` (search-path injection
    surface for a SECURITY-sensitive trigger fn) → pinned to ``pg_catalog, public``.
  - C5:  the single-super_admin partial unique index (0006) pins to a literal
    UUID, but nothing stopped the ``super_admin`` platform role row itself from
    being recreated with a *different* id (which would silently disable the
    index). A CHECK constraint now pins the platform ``super_admin`` system role
    to the well-known id ``…00a1``.
  - H10: the ≥1-owner floor was service-only (a count-then-delete with a TOCTOU
    window — two workspace_admins could each revoke a different owner grant
    concurrently and drive the workspace to zero owners). A ``BEFORE DELETE``
    trigger with ``SELECT … FOR UPDATE`` on the workspace's owner role row
    serialises concurrent revokes so the loser sees ``last_owner`` and rolls
    back. The trigger is skipped for cascade-originated deletes (e.g. deleting
    an ``auth.users`` row cascades into ``user_roles``) via ``pg_trigger_depth``.
  - 6.2.7: ``tenant_memberships`` FOR-ALL owner/admin policy split into explicit
    per-action policies (SELECT visible to any tenant member; writes restricted
    to owner/admin). Defense-in-depth refinement; the backend request path is
    the primary gate.

NOTE (deferred to PAR-C slice 2): the ``granted_by NOT NULL`` + system-sentinel
change, the privilege-escalation trigger broadening / bypass role-gating, and
the separate ``xtrusio_reconciler`` DB role are intentionally NOT in this
migration. They are coupled: ``granted_by`` is ``REFERENCES auth.users(id) ON
DELETE SET NULL`` (NOT NULL conflicts with SET NULL) and the system-grant paths
(onboarding / invite-accept / bootstrap) currently rely on the
``granted_by IS NULL`` trigger short-circuit. Reworking that marker + minting a
reconciler role on managed Supabase is its own slice.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The platform super_admin system role's pinned id (matches the 0006 seed and
# the single-super_admin partial unique index predicate).
_SUPER_ADMIN_ROLE_ID = "00000000-0000-0000-0000-0000000000a1"


def upgrade() -> None:
    # --- M17: pin search_path on set_updated_at() -------------------------
    # The fn body only touches NEW, but a SECURITY-sensitive trigger fn with an
    # unpinned search_path is a hardening gap. SECURITY INVOKER (default) is
    # kept — it does no privileged work.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END
        $$;
        """
    )

    # --- C5: pin the platform super_admin system role id ------------------
    # Belt to the single-super_admin partial index's suspenders: that index can
    # only enforce "one super_admin grant" if the super_admin role keeps the id
    # its predicate references. This CHECK makes recreating the platform
    # super_admin system role under a different id impossible.
    op.execute(
        f"""
        ALTER TABLE roles ADD CONSTRAINT roles_super_admin_pinned_id CHECK (
            (key = 'super_admin' AND scope = 'platform' AND is_system
             AND id = '{_SUPER_ADMIN_ROLE_ID}')
            OR key != 'super_admin'
            OR scope != 'platform'
        )
        """
    )

    # --- H10: workspace ≥1-owner floor as a DB trigger --------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_workspace_owner_floor()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            remaining_owners int;
            tgt_workspace uuid;
        BEGIN
            -- System processes (test-suite purge, boot reconciler) opt out
            -- explicitly. Mirrors the 0009 governance triggers. Backend REQUEST
            -- code MUST NEVER set this GUC.
            IF current_setting('app.bypass_priv_escalation', true) = 'on' THEN
                RETURN OLD;
            END IF;

            -- Skip cascade-originated deletes (depth > 1 means we're nested
            -- inside another trigger, e.g. the FK cascade fired by deleting an
            -- auth.users row or a tenant — deleting a sole-owner user must not
            -- be blocked by the floor). Only direct revokes (depth = 1) enforce.
            IF pg_trigger_depth() > 1 THEN
                RETURN OLD;
            END IF;

            -- The floor guards the ACTOR-DRIVEN application revoke path (which
            -- sets app.actor_id) — that is where the H10 two-admin race lives.
            -- A delete with no actor is a system/teardown operation (test
            -- cleanup, ad-hoc maintenance), consistent with how the 0009
            -- priv-escalation trigger treats actor-less grants. Skip it.
            IF nullif(current_setting('app.actor_id', true), '') IS NULL THEN
                RETURN OLD;
            END IF;

            -- Only owner-role grants matter.
            IF OLD.role_id NOT IN (
                SELECT id FROM roles WHERE key = 'owner' AND scope = 'workspace'
            ) THEN
                RETURN OLD;
            END IF;

            tgt_workspace := OLD.workspace_id;

            -- Serialise concurrent owner revokes for this workspace: lock the
            -- workspace's owner role row so the count below can't race.
            PERFORM 1 FROM roles
            WHERE scope = 'workspace' AND workspace_id = tgt_workspace AND key = 'owner'
            FOR UPDATE;

            SELECT count(*) INTO remaining_owners
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.workspace_id = tgt_workspace
              AND r.scope = 'workspace'
              AND r.key = 'owner'
              AND ur.id != OLD.id;

            IF remaining_owners = 0 THEN
                RAISE EXCEPTION 'last_owner'
                  USING ERRCODE = 'check_violation';
            END IF;

            RETURN OLD;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_user_roles_owner_floor
        BEFORE DELETE ON user_roles
        FOR EACH ROW EXECUTE FUNCTION enforce_workspace_owner_floor();
        """
    )

    # --- 6.2.7: tenant_memberships per-action RLS -------------------------
    # Replace the FOR-ALL owner/admin policy with explicit per-action policies.
    # SELECT becomes visible to any member of the tenant (co-members can see
    # each other); writes stay owner/admin-only. The pre-existing
    # tenant_memberships_self_read (SELECT, self) and
    # tenant_memberships_super_admin_all (FOR ALL, super_admin) policies are
    # left intact and OR with these (permissive policies union).
    op.execute("DROP POLICY tenant_memberships_owner_admin_manage ON tenant_memberships")
    op.execute(
        """
        CREATE POLICY tenant_memberships_member_select ON tenant_memberships
            FOR SELECT TO authenticated
            USING (is_tenant_member(auth.uid(), tenant_id))
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_memberships_owner_admin_insert ON tenant_memberships
            FOR INSERT TO authenticated
            WITH CHECK (is_tenant_owner_or_admin(auth.uid(), tenant_id))
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_memberships_owner_admin_update ON tenant_memberships
            FOR UPDATE TO authenticated
            USING (is_tenant_owner_or_admin(auth.uid(), tenant_id))
            WITH CHECK (is_tenant_owner_or_admin(auth.uid(), tenant_id))
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_memberships_owner_admin_delete ON tenant_memberships
            FOR DELETE TO authenticated
            USING (is_tenant_owner_or_admin(auth.uid(), tenant_id))
        """
    )


def downgrade() -> None:
    # --- 6.2.7 reverse: restore the FOR-ALL owner/admin policy ------------
    op.execute("DROP POLICY IF EXISTS tenant_memberships_member_select ON tenant_memberships")
    op.execute("DROP POLICY IF EXISTS tenant_memberships_owner_admin_insert ON tenant_memberships")
    op.execute("DROP POLICY IF EXISTS tenant_memberships_owner_admin_update ON tenant_memberships")
    op.execute("DROP POLICY IF EXISTS tenant_memberships_owner_admin_delete ON tenant_memberships")
    op.execute(
        """
        CREATE POLICY tenant_memberships_owner_admin_manage ON tenant_memberships
            FOR ALL TO authenticated
            USING (is_tenant_owner_or_admin(auth.uid(), tenant_id))
            WITH CHECK (is_tenant_owner_or_admin(auth.uid(), tenant_id))
        """
    )

    # --- H10 reverse ------------------------------------------------------
    op.execute("DROP TRIGGER IF EXISTS trg_user_roles_owner_floor ON user_roles")
    op.execute("DROP FUNCTION IF EXISTS enforce_workspace_owner_floor()")

    # --- C5 reverse -------------------------------------------------------
    op.execute("ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_super_admin_pinned_id")

    # --- M17 reverse: restore set_updated_at() without pinned search_path -
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END
        $$;
        """
    )
