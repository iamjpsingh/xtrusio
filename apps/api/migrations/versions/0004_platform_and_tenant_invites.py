"""platform_invites + tenant_invites tables with RLS

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-15

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Invites are immutable except for the accepted_at / revoked_at lifecycle
# timestamps, which fully capture state transitions — no updated_at column
# (and thus no set_updated_at trigger) is needed, unlike the core entity tables.
def upgrade() -> None:
    # platform_invites — super_admin can only invite admin / editor (never super_admin).
    op.execute(
        """
        CREATE TABLE platform_invites (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email       citext NOT NULL,
            role        platform_role NOT NULL CHECK (role IN ('admin', 'editor')),
            invited_by  uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
            expires_at  timestamptz NOT NULL,
            accepted_at timestamptz,
            revoked_at  timestamptz,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX platform_invites_email_pending_uq
            ON platform_invites(email)
            WHERE accepted_at IS NULL AND revoked_at IS NULL
        """
    )

    # tenant_invites — owner/admin invites; cannot invite owner.
    op.execute(
        """
        CREATE TABLE tenant_invites (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email       citext NOT NULL,
            role        tenant_role NOT NULL CHECK (role IN ('admin', 'editor', 'read_only')),
            invited_by  uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
            expires_at  timestamptz NOT NULL,
            accepted_at timestamptz,
            revoked_at  timestamptz,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX tenant_invites_tenant_id_idx ON tenant_invites(tenant_id)")
    op.execute(
        """
        CREATE UNIQUE INDEX tenant_invites_email_pending_uq
            ON tenant_invites(tenant_id, email)
            WHERE accepted_at IS NULL AND revoked_at IS NULL
        """
    )

    # Alembic-created tables do not inherit Supabase's auto-grants to the
    # `authenticated` role; RLS is evaluated only after table-level privilege.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON platform_invites, tenant_invites TO authenticated"
    )

    # RLS — platform_invites. Use the SECURITY DEFINER helper from 0003
    # (never inline EXISTS on platform_users — that recurses under RLS).
    # RLS note: invite acceptance is backend-mediated — FastAPI's
    # /api/invites/accept reads the invite row via the app's owner DB
    # connection (not the `authenticated` role) and inserts the membership.
    # Invitees never SELECT these tables under `authenticated`, so there is
    # deliberately NO invitee-facing read policy (one keyed by email would
    # allow enumeration of pending invites). Only managers (super_admin /
    # tenant owner-admin) get row access, via the 0003 SECURITY DEFINER helpers.
    op.execute("ALTER TABLE platform_invites ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY platform_invites_super_admin_all ON platform_invites
            FOR ALL TO authenticated
            USING (is_super_admin(auth.uid()))
            WITH CHECK (is_super_admin(auth.uid()))
        """
    )

    # RLS — tenant_invites. super_admin (helper) OR tenant owner/admin (helper).
    op.execute("ALTER TABLE tenant_invites ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_invites_super_admin_all ON tenant_invites
            FOR ALL TO authenticated
            USING (is_super_admin(auth.uid()))
            WITH CHECK (is_super_admin(auth.uid()))
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_invites_owner_admin_all ON tenant_invites
            FOR ALL TO authenticated
            USING (is_tenant_owner_or_admin(auth.uid(), tenant_id))
            WITH CHECK (is_tenant_owner_or_admin(auth.uid(), tenant_id))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_invites_owner_admin_all ON tenant_invites")
    op.execute("DROP POLICY IF EXISTS tenant_invites_super_admin_all ON tenant_invites")
    op.execute("DROP POLICY IF EXISTS platform_invites_super_admin_all ON platform_invites")
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON platform_invites, tenant_invites FROM authenticated"
    )
    op.execute("DROP TABLE IF EXISTS tenant_invites")
    op.execute("DROP TABLE IF EXISTS platform_invites")
