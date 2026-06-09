"""DB-level triggers added in migration 0009.

These tests exercise the triggers directly via raw SQL. The service-layer
guards (P4-B2/P4-C1) are defense-in-depth on top of these triggers.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_priv_escalation_rejects_grant_when_actor_lacks_target_perms(
    db_session: AsyncSession,
) -> None:
    """An actor with NO grants cannot INSERT user_roles for the platform `admin` role."""
    actor_id = uuid4()
    target_id = uuid4()
    # Seed two @example.com auth users with NO user_roles grants.
    for uid in (actor_id, target_id):
        await db_session.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
                "'authenticated', :email, '', now(), now(), now())"
            ),
            {"id": str(uid), "email": f"esc-{uid.hex[:8]}@example.com"},
        )
    await db_session.commit()

    # Resolve the platform `admin` system role id.
    role_id = (
        await db_session.execute(
            text("SELECT id FROM roles WHERE scope='platform' AND key='admin' AND is_system")
        )
    ).scalar_one()

    await db_session.execute(
        text("SELECT set_config('app.actor_id', :a, true)"),
        {"a": str(actor_id)},
    )
    with pytest.raises(DBAPIError) as exc:
        await db_session.execute(
            text(
                "INSERT INTO user_roles (auth_user_id, role_id, granted_by) " "VALUES (:u, :r, :g)"
            ),
            {"u": str(target_id), "r": str(role_id), "g": str(actor_id)},
        )
    assert "privilege" in str(exc.value).lower()
    await db_session.rollback()


async def test_priv_escalation_allows_grant_when_actor_holds_target_perms(
    db_session: AsyncSession,
    existing_super_admin: PlatformUser,
) -> None:
    """super_admin (holds every platform perm) can grant platform 'admin'."""
    # existing_super_admin fixture comes from conftest.py - the live operator
    # account, never created/deleted by tests.
    target_id = uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) "
            "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
            "'authenticated', :email, '', now(), now(), now())"
        ),
        {"id": str(target_id), "email": f"esc-ok-{target_id.hex[:8]}@example.com"},
    )
    await db_session.commit()
    role_id = (
        await db_session.execute(
            text("SELECT id FROM roles WHERE scope='platform' AND key='admin' AND is_system")
        )
    ).scalar_one()
    await db_session.execute(
        text("SELECT set_config('app.actor_id', :a, true)"),
        {"a": str(existing_super_admin.id)},
    )
    await db_session.execute(
        text("INSERT INTO user_roles (auth_user_id, role_id, granted_by) " "VALUES (:u, :r, :g)"),
        {"u": str(target_id), "r": str(role_id), "g": str(existing_super_admin.id)},
    )
    # Should succeed. Clean up.
    await db_session.execute(
        text("DELETE FROM user_roles WHERE auth_user_id = :u"), {"u": str(target_id)}
    )
    await db_session.commit()


async def test_null_granted_by_auto_bypasses_priv_escalation(
    db_session: AsyncSession,
) -> None:
    """System / bootstrap grants set granted_by=NULL — trigger auto-bypasses.

    Onboarding, invite-acceptance, bootstrap, and the boot reconciler all use
    granted_by=NULL. Only P4's grant API sets granted_by=actor_id, which is
    where the trigger enforces.
    """
    target_id = uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) "
            "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
            "'authenticated', :email, '', now(), now(), now())"
        ),
        {"id": str(target_id), "email": f"null-by-{target_id.hex[:8]}@example.com"},
    )
    await db_session.commit()
    role_id = (
        await db_session.execute(
            text("SELECT id FROM roles WHERE scope='platform' AND key='admin' AND is_system")
        )
    ).scalar_one()
    # No app.actor_id set, no bypass GUC — granted_by=NULL alone should pass.
    await db_session.execute(
        text("INSERT INTO user_roles (auth_user_id, role_id, granted_by) VALUES (:u, :r, NULL)"),
        {"u": str(target_id), "r": str(role_id)},
    )
    await db_session.execute(
        text("DELETE FROM user_roles WHERE auth_user_id = :u"), {"u": str(target_id)}
    )
    await db_session.commit()


async def test_bypass_guc_allows_grant_without_actor(db_session: AsyncSession) -> None:
    """The reconciler boot path uses app.bypass_priv_escalation = on."""
    target_id = uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) "
            "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
            "'authenticated', :email, '', now(), now(), now())"
        ),
        {"id": str(target_id), "email": f"bypass-{target_id.hex[:8]}@example.com"},
    )
    await db_session.commit()
    role_id = (
        await db_session.execute(
            text("SELECT id FROM roles WHERE scope='platform' AND key='admin' AND is_system")
        )
    ).scalar_one()
    await db_session.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
    await db_session.execute(
        text("INSERT INTO user_roles (auth_user_id, role_id, granted_by) " "VALUES (:u, :r, NULL)"),
        {"u": str(target_id), "r": str(role_id)},
    )
    # Cleanup.
    await db_session.execute(
        text("DELETE FROM user_roles WHERE auth_user_id = :u"), {"u": str(target_id)}
    )
    await db_session.commit()


async def test_immutable_system_role_rejects_update(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError) as exc:
        await db_session.execute(
            text(
                "UPDATE roles SET name = 'pwned' "
                "WHERE scope='platform' AND key='super_admin' AND is_system"
            )
        )
    assert "system role" in str(exc.value).lower() and "immutable" in str(exc.value).lower()
    await db_session.rollback()


async def test_immutable_system_role_rejects_delete(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("DELETE FROM roles " "WHERE scope='platform' AND key='super_admin' AND is_system")
        )
    await db_session.rollback()


async def test_immutable_system_role_rejects_role_perm_change(
    db_session: AsyncSession,
) -> None:
    """PLATFORM-scope is_system role permissions are immutable."""
    row = (
        await db_session.execute(
            text(
                "SELECT rp.role_id, rp.permission_id FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "WHERE r.is_system AND r.scope='platform' LIMIT 1"
            )
        )
    ).first()
    assert row is not None, "no platform-system role_permissions found — DB not seeded"
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("DELETE FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
            {"r": str(row.role_id), "p": str(row.permission_id)},
        )
    await db_session.rollback()


async def test_workspace_system_roles_are_mutable_for_workspace_lifecycle(
    db_session: AsyncSession,
) -> None:
    """Workspace-scope is_system roles are per-workspace data and must allow
    DELETE so a tenant deletion can cascade through its roles.

    Spec section 3.3: workspace system roles are 'instantiated per workspace'. Their
    immutability is enforced by the application via the workspace.roles.manage
    permission gate (P5), not by the DB trigger.
    """
    # Find a workspace-scope is_system role and a permission attached to it.
    # If no tenant exists, the test is vacuous (skip).
    row = (
        await db_session.execute(
            text(
                "SELECT rp.role_id, rp.permission_id FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "WHERE r.is_system AND r.scope='workspace' LIMIT 1"
            )
        )
    ).first()
    if row is None:
        pytest.skip("no workspace tenants/roles present — vacuous")
    # DELETE on workspace system role_permissions should NOT raise.
    # We rollback to avoid actually mutating seeded state.
    await db_session.execute(
        text("DELETE FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
        {"r": str(row.role_id), "p": str(row.permission_id)},
    )
    await db_session.rollback()
