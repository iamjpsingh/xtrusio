"""RBAC governance triggers: privilege-escalation + immutable system roles.

Spec §6.1 (privilege-escalation guard, defense in depth at the DB layer) and
§6.3 (immutable system roles).

`enforce_priv_escalation` reads the actor from session GUC `app.actor_id`. A
boot-time reconciler (reconcile_user_roles_from_enums) cannot meaningfully
identify "an actor" — it's a system process — so it sets the bypass GUC
`app.bypass_priv_escalation = 'on'` before its INSERTs. Backend request code
MUST NEVER set the bypass GUC; the request handler sets `app.actor_id` to the
authenticated user instead.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Privilege-escalation enforcement on INSERT into user_roles.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_priv_escalation()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
            actor_id uuid;
            target_scope text;
            target_workspace_id uuid;
            missing_perm text;
        BEGIN
            -- System reconcilers (boot, alembic) opt out explicitly. Backend
            -- request code MUST NEVER set this GUC.
            IF current_setting('app.bypass_priv_escalation', true) = 'on' THEN
                RETURN NEW;
            END IF;

            -- System / bootstrap grants set granted_by = NULL (reconciler,
            -- onboarding, invite-acceptance, bootstrap script). The priv-
            -- escalation rule applies only to human-actor grants (P4's grant
            -- API), which always sets granted_by to the actor's user id.
            -- Direct-DB attackers who can forge granted_by = NULL already have
            -- privileged DB access; this trigger is defense-in-depth on the
            -- application path, not a sole control.
            IF NEW.granted_by IS NULL THEN
                RETURN NEW;
            END IF;

            actor_id := nullif(current_setting('app.actor_id', true), '')::uuid;

            SELECT r.scope, NEW.workspace_id
              INTO target_scope, target_workspace_id
              FROM roles r WHERE r.id = NEW.role_id;

            -- Find ANY permission in the target role that the actor does NOT hold.
            SELECT p.key INTO missing_perm
            FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = NEW.role_id
              AND NOT (
                CASE target_scope
                  WHEN 'platform' THEN has_platform_perm(actor_id, p.key)
                  WHEN 'workspace' THEN has_workspace_perm(actor_id, target_workspace_id, p.key)
                  ELSE false
                END
              )
            LIMIT 1;

            IF missing_perm IS NOT NULL THEN
                RAISE EXCEPTION
                  'privilege escalation denied: actor lacks permission %', missing_perm
                  USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN NEW;
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_user_roles_priv_escalation
        BEFORE INSERT ON user_roles
        FOR EACH ROW EXECUTE FUNCTION enforce_priv_escalation();
        """
    )

    # Immutable system roles: block UPDATE/DELETE on roles where is_system.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_system_role_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            -- System reconcilers / cascade-delete-from-tenants paths bypass
            -- via the same GUC used by enforce_priv_escalation. Backend
            -- request code MUST NEVER set this GUC.
            IF current_setting('app.bypass_priv_escalation', true) = 'on' THEN
                RETURN COALESCE(NEW, OLD);
            END IF;
            IF (TG_OP IN ('UPDATE','DELETE')) AND (OLD.is_system) THEN
                RAISE EXCEPTION
                  'system role is immutable (role.id=%)', OLD.id
                  USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_roles_immutable_system
        BEFORE UPDATE OR DELETE ON roles
        FOR EACH ROW EXECUTE FUNCTION reject_system_role_mutation();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_system_role_perm_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            role_is_system boolean;
            target_role_id uuid;
        BEGIN
            -- System reconcilers re-seed role_permissions for is_system roles;
            -- bypass via the same GUC used by enforce_priv_escalation.
            IF current_setting('app.bypass_priv_escalation', true) = 'on' THEN
                RETURN COALESCE(NEW, OLD);
            END IF;
            target_role_id := COALESCE(NEW.role_id, OLD.role_id);
            SELECT is_system INTO role_is_system FROM roles WHERE id = target_role_id;
            IF role_is_system THEN
                RAISE EXCEPTION
                  'system role permissions are immutable (role.id=%)', target_role_id
                  USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_role_perms_immutable_system
        BEFORE INSERT OR UPDATE OR DELETE ON role_permissions
        FOR EACH ROW EXECUTE FUNCTION reject_system_role_perm_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_user_roles_priv_escalation ON user_roles;")
    op.execute("DROP TRIGGER IF EXISTS trg_roles_immutable_system ON roles;")
    op.execute("DROP TRIGGER IF EXISTS trg_role_perms_immutable_system ON role_permissions;")
    op.execute("DROP FUNCTION IF EXISTS enforce_priv_escalation();")
    op.execute("DROP FUNCTION IF EXISTS reject_system_role_mutation();")
    op.execute("DROP FUNCTION IF EXISTS reject_system_role_perm_change();")
