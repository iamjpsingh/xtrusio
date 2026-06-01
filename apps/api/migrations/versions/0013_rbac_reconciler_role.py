"""PAR-C slice 2: reconciler DB-role isolation + role-gated bypass GUC.

Closes audit findings:
  - **M15** — the boot/CLI reconciler set ``app.bypass_priv_escalation = 'on'``
    on the SAME ``postgres`` connection the request path uses. A dedicated,
    minimally-privileged ``xtrusio_reconciler`` role now carries the reconcile
    work; the request path stays on ``postgres``.
  - **C4** (role-gate + INSERT-only halves) — ``enforce_priv_escalation``
    (0009) honoured the bypass GUC from ANY role and only fired on INSERT. It
    now (a) gates the bypass on ``current_user = 'xtrusio_reconciler'`` so a GUC
    set on the request path is INERT *for this trigger*, and (b) fires on
    ``INSERT OR UPDATE`` so a future role-transfer feature can't slip a
    privilege change past it. **Critical**: the function is recreated
    ``SECURITY INVOKER`` (0009 had it ``SECURITY DEFINER``). Under DEFINER
    ``current_user`` is the function OWNER (``postgres``), so the role-gate
    could never match — the gate only works when ``current_user`` reflects the
    SESSION role.
  - **H9** (DB half) — the role isolation plus the PAR-B ``checkin`` listener
    (db.py) that RESETs ``app.actor_id`` / ``app.bypass_priv_escalation`` mean
    no actor/bypass state leaks across pooled connections. The application half
    — collapsing the four duplicate ``_set_actor`` helpers into one shared
    ``core.permissions.set_actor`` — ships in the same PR.

SCOPE OF THE ROLE-GATE (do not overclaim): ONLY ``enforce_priv_escalation`` is
role-gated here. The 0009 system-role immutability triggers
(``reject_system_role_mutation``, ``reject_system_role_perm_change``) and the
0010 ``enforce_workspace_owner_floor`` still honour ``app.bypass_priv_escalation
= 'on'`` from ANY role, BY DESIGN: onboarding's ``wire_workspace_role_perms``
re-seeds is_system ``role_permissions`` on the request path and the test-purge
opts out of the owner floor — both need the un-gated bypass. Role-gating those
is deferred (out of C4 scope per spec §6.2.1/§6.2.2); no shipped request-path
code sets the GUC, and ``require_permission()`` remains the primary gate.

RLS NOTE (why the policies below exist): the backend bypasses RLS by connecting
as the table OWNER (``postgres``). ``xtrusio_reconciler`` is a non-owner role,
so without explicit policies RLS would deny it every read (0 rows) and write on
the RBAC + projection tables. ``ALTER ROLE ... BYPASSRLS`` needs superuser
(managed-Supabase ``postgres`` is not one), so we instead add permissive
``FOR ALL TO xtrusio_reconciler`` policies on exactly the tables reconcile
touches. (For ``user_roles`` the priv-escalation trigger still governs
escalation safety; ``USING/WITH CHECK true`` only lifts RLS.)

DEFERRED to a live-DB slice (deliberately NOT in this migration), with rationale:
  - §6.2.3 ``granted_by NOT NULL`` + system sentinel. ``user_roles.granted_by``
    is ``REFERENCES auth.users(id) ON DELETE SET NULL`` — NOT NULL conflicts
    with ``SET NULL``, and the sentinel's FK target is the Supabase-owned
    ``auth.users`` table. Worse, onboarding (``create_tenant_with_owner``) and
    invite-acceptance self-grant via ``grant_role(granted_by=None)`` and depend
    on the ``granted_by IS NULL`` short-circuit below (a brand-new principal
    holds no perms, so the perm-walk would reject them). Dropping that branch
    without rerouting those request-path flows would break onboarding AND
    invite-accept — unsafe to land without a live DB to validate. The
    short-circuit is therefore KEPT here, documented as the request-path
    system-grant marker.

OPERATOR STEP (post-migrate, out of band — NO secret in source):
    ALTER ROLE xtrusio_reconciler LOGIN PASSWORD '<strong-password>';
  then set ``RECONCILE_DATABASE_URL`` to a DSN for that role. Until then the
  reconciler transparently falls back to the request engine (dev-safe) and logs
  a warning. The role is created ``NOLOGIN`` here precisely so this migration
  carries no credential. **The production RECONCILE_DATABASE_URL path must be
  smoke-tested against a live DB before reliance** (it cannot be exercised in
  dev, where reconcile runs as ``postgres``/owner). See
  ``docs/superpowers/HANDOFF.md``.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RECONCILER_ROLE = "xtrusio_reconciler"

# Every table the reconciler (rbac/reconcile.py) reads or writes. All are
# RLS-enabled (0001/0002/0006), so each needs a permissive policy for the
# non-owner reconciler role.
_RECONCILER_TABLES = (
    "permissions",
    "roles",
    "role_permissions",
    "user_roles",
    "tenants",
    "platform_users",
    "tenant_memberships",
)


def upgrade() -> None:
    # --- M15: create the least-privileged reconciler role -----------------
    # Idempotent (re-runnable) and credential-free: NOLOGIN until the operator
    # flips it to LOGIN + password out of band.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_RECONCILER_ROLE}') THEN
                CREATE ROLE {_RECONCILER_ROLE} NOLOGIN NOSUPERUSER;
            END IF;
        END
        $$;
        """
    )
    # Least privilege: DML only, no DDL/superuser. (No GRANT SET ON PARAMETER —
    # custom placeholder GUCs are session-settable by any role regardless, and
    # GRANT on a parameter requires superuser on managed Supabase, which would
    # abort the migration. The trigger's current_user role-gate is the control.)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_RECONCILER_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_RECONCILER_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {_RECONCILER_ROLE}"
    )

    # --- M15: permissive RLS policies so the non-owner reconciler can work --
    # Without these, RLS (owner-bypass only) denies the reconciler every read
    # (0 rows -> silent mis-reconciliation) and every write on these tables.
    for tbl in _RECONCILER_TABLES:
        op.execute(
            f"CREATE POLICY {tbl}_reconciler_all ON {tbl} "
            f"FOR ALL TO {_RECONCILER_ROLE} USING (true) WITH CHECK (true)"
        )

    # --- C4: role-gate the bypass GUC + broaden trigger to INSERT OR UPDATE
    # SECURITY INVOKER is REQUIRED (see module docstring): under SECURITY
    # DEFINER `current_user` would be the function owner, never the session
    # role, so the role-gate could never fire. The perm-walk still works because
    # has_platform_perm / has_workspace_perm (0007) are themselves SECURITY
    # DEFINER and run with their own privileges regardless of the caller.
    op.execute("DROP TRIGGER IF EXISTS trg_user_roles_priv_escalation ON user_roles")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION enforce_priv_escalation()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            actor_id uuid;
            target_scope text;
            target_workspace_id uuid;
            missing_perm text;
        BEGIN
            -- ROLE-GATED bypass: only the dedicated reconciler login role may
            -- bypass, and only when it explicitly sets the GUC. A GUC set on
            -- the request path (current_user = 'postgres') is INERT here.
            IF current_user = '{_RECONCILER_ROLE}'
               AND current_setting('app.bypass_priv_escalation', true) = 'on' THEN
                RETURN NEW;
            END IF;

            -- Request-path system grants — onboarding's owner self-grant and
            -- invite-acceptance — set granted_by = NULL and rely on this
            -- short-circuit (a brand-new principal holds no perms, so the
            -- perm-walk below would reject them). The grant API ALWAYS sets
            -- granted_by to the actor's id, so this branch never relaxes the
            -- human-actor path. KEPT pending the §6.2.3 sentinel rework — see
            -- the migration docstring for why dropping it now would break
            -- onboarding + invite-accept.
            IF NEW.granted_by IS NULL THEN
                RETURN NEW;
            END IF;

            actor_id := nullif(current_setting('app.actor_id', true), '')::uuid;

            SELECT r.scope, NEW.workspace_id
              INTO target_scope, target_workspace_id
              FROM roles r WHERE r.id = NEW.role_id;

            -- Find ANY permission in the target role the actor does NOT hold.
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
        BEFORE INSERT OR UPDATE ON user_roles
        FOR EACH ROW EXECUTE FUNCTION enforce_priv_escalation();
        """
    )


def downgrade() -> None:
    # --- C4 reverse: restore the 0009 trigger (INSERT only, DEFINER, any-role
    # bypass, search_path = public). -------------------------------------
    op.execute("DROP TRIGGER IF EXISTS trg_user_roles_priv_escalation ON user_roles")
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
            IF current_setting('app.bypass_priv_escalation', true) = 'on' THEN
                RETURN NEW;
            END IF;
            IF NEW.granted_by IS NULL THEN
                RETURN NEW;
            END IF;
            actor_id := nullif(current_setting('app.actor_id', true), '')::uuid;
            SELECT r.scope, NEW.workspace_id
              INTO target_scope, target_workspace_id
              FROM roles r WHERE r.id = NEW.role_id;
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

    # --- M15 reverse: drop policies + grants + role. Revoke before DROP ROLE
    # so no dependent privileges block it. -------------------------------
    for tbl in _RECONCILER_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_reconciler_all ON {tbl}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {_RECONCILER_ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {_RECONCILER_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {_RECONCILER_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {_RECONCILER_ROLE}")
