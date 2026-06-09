"""Retire the transition-safe enum disjunct: rewrite the three 0007 helpers
(is_super_admin/is_tenant_owner_or_admin/is_tenant_member) from the
`resolver OR 0003-enum` form to PURE resolver — completing the enum->resolver
cutover.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-19

Spec: docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md section 5.
Pure raw SQL. Safe because merged P3a made every principal resolver-visible
and merged P3b made the backend resolver-authoritative; the legacy enum
fallback is now redundant. Same signatures + SECURITY DEFINER STABLE SET
search_path = public → every existing 0003/0004/0007 policy that calls them
is untouched. downgrade() restores the exact 0007 transition-safe bodies
(fully reversible).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # M20 ordering guard: 0008 retires the enum fallback, so every principal
    # MUST already be resolver-visible (i.e. backfilled into user_roles by 0006
    # + the reconciler). Refuse to upgrade a populated DB whose user_roles is
    # still empty — running 0008 there would silently strip super_admin/owner
    # access. A no-op on a correctly-migrated DB (user_roles populated) and on a
    # fresh DB (platform_users empty).
    bind = op.get_bind()
    user_role_count = bind.execute(text("SELECT count(*) FROM user_roles")).scalar()
    platform_user_count = bind.execute(text("SELECT count(*) FROM platform_users")).scalar()
    if platform_user_count and not user_role_count:
        raise RuntimeError(
            "0008 expects user_roles to be backfilled (run 0006 + reconciler). "
            "Refusing to upgrade on a populated DB with empty user_roles."
        )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_super_admin(uid uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$ SELECT has_platform_perm(uid, 'platform.roles.manage') $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_owner_or_admin(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$ SELECT has_workspace_perm(uid, tid, 'workspace.members.manage') $$
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
        $$
        """
    )


def downgrade() -> None:
    # Restore the EXACT 0007 transition-safe `resolver OR 0003-enum` bodies
    # (byte-for-byte from 0007_rls_permission_engine.py lines 114-158).
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
