"""RBAC foundation: dynamic roles/permissions, system-role seed, enum backfill.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-17

Spec: docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md (§3, §6, §7).
Pure raw SQL (codebase convention). Permission catalog rows + system-role
role_permissions are projected by the reconciler (xtrusio_api.rbac.reconcile),
NOT this migration — see plan Architecture note.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- permissions -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE permissions (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            scope         text NOT NULL CHECK (scope IN ('platform','workspace')),
            key           text NOT NULL UNIQUE,
            category      text NOT NULL,
            description   text NOT NULL,
            is_deprecated boolean NOT NULL DEFAULT false
        )
        """
    )

    # --- roles -------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE roles (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            scope        text NOT NULL CHECK (scope IN ('platform','workspace')),
            workspace_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
            key          text NOT NULL,
            name         text NOT NULL,
            description  text NOT NULL DEFAULT '',
            is_system    boolean NOT NULL DEFAULT false,
            created_by   uuid REFERENCES auth.users(id) ON DELETE SET NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT roles_scope_workspace_ck CHECK (
                (scope = 'platform' AND workspace_id IS NULL)
                OR (scope = 'workspace' AND workspace_id IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX roles_scope_ws_key_uq "
        "ON roles (scope, COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'), key)"
    )
    op.execute(
        "CREATE TRIGGER roles_set_updated_at BEFORE UPDATE ON roles "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # --- role_permissions --------------------------------------------------
    op.execute(
        """
        CREATE TABLE role_permissions (
            role_id       uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
            PRIMARY KEY (role_id, permission_id)
        )
        """
    )

    # --- user_roles --------------------------------------------------------
    op.execute(
        """
        CREATE TABLE user_roles (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            auth_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            role_id      uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            workspace_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
            granted_by   uuid REFERENCES auth.users(id) ON DELETE SET NULL,
            granted_at   timestamptz NOT NULL DEFAULT now(),
            UNIQUE (auth_user_id, role_id, workspace_id)
        )
        """
    )
    op.execute("CREATE INDEX user_roles_auth_user_id_idx ON user_roles(auth_user_id)")
    op.execute("CREATE INDEX user_roles_role_id_idx ON user_roles(role_id)")

    # Single-super_admin DB invariant: at most one grant of the platform
    # super_admin system role. A partial-index predicate must be immutable and
    # reference only the indexed table (Postgres forbids subqueries in index
    # predicates), so the super_admin system role is seeded (Task 4) with a
    # fixed well-known id and the predicate pins to that constant. Mirrors the
    # `id = 1` singleton pattern in migration 0002 — a structural sentinel,
    # not env-varying config.
    op.execute(
        "CREATE UNIQUE INDEX user_roles_one_super_admin ON user_roles ((true)) "
        "WHERE role_id = '00000000-0000-0000-0000-0000000000a1'"
    )

    # --- rbac_audit_log ----------------------------------------------------
    op.execute(
        """
        CREATE TABLE rbac_audit_log (
            id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            actor_auth_user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
            action             text NOT NULL,
            target_type        text NOT NULL,
            target_id          text NOT NULL,
            scope              text NOT NULL CHECK (scope IN ('platform','workspace')),
            workspace_id       uuid REFERENCES tenants(id) ON DELETE CASCADE,
            before             jsonb,
            after              jsonb,
            created_at         timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    # --- RLS enable (real perm-aware policies are authored in P2) ----------
    for tbl in ("permissions", "roles", "role_permissions", "user_roles", "rbac_audit_log"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")

    # Minimal interim read policy so authenticated callers are not hard-denied
    # before P2 authors the real perm-aware policies. SELECT-only; writes go
    # through the owner backend connection (RLS does not constrain it).
    for tbl in ("permissions", "roles", "role_permissions", "user_roles"):
        op.execute(
            f"CREATE POLICY {tbl}_authenticated_read ON {tbl} "
            f"FOR SELECT TO authenticated USING (true)"
        )
    op.execute(
        "CREATE POLICY rbac_audit_log_no_read ON rbac_audit_log "
        "FOR SELECT TO authenticated USING (false)"
    )

    # DML grants — Alembic tables don't inherit Supabase auto-grants.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "permissions, roles, role_permissions, user_roles, rbac_audit_log "
        "TO authenticated"
    )

    # Seeds + backfill: added in Task 4 BELOW THIS LINE (same upgrade()).


def downgrade() -> None:
    op.execute("ALTER TABLE tenant_invites DROP COLUMN IF EXISTS role_id")
    op.execute("ALTER TABLE platform_invites DROP COLUMN IF EXISTS role_id")
    op.execute("DROP TABLE IF EXISTS rbac_audit_log")
    op.execute("DROP TABLE IF EXISTS role_permissions")
    op.execute("DROP TABLE IF EXISTS user_roles")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("DROP TABLE IF EXISTS permissions")
