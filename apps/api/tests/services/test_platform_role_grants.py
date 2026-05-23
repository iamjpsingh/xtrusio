"""Service-layer tests for platform-role grant/revoke.

Actor for every test is the real ``existing_super_admin`` (read-only fixture;
per the test-data hygiene rule we NEVER create a super_admin in tests). Custom
roles + ephemeral @example.com users are torn down in ``try/finally`` blocks;
the @example.com convention also lets ``_cleanup.py`` sweep anything we miss.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser
from xtrusio_api.services.platform_role_grants import (
    GrantNotFoundError,
    PlatformUserNotFoundError,
    PrivilegeEscalationError,
    RoleNotFoundError,
    RoleScopeMismatchError,
    SingleSuperAdminError,
    grant_platform_role,
    list_platform_role_grants,
    revoke_platform_role_grant,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


# --- helpers ---------------------------------------------------------------


async def _create_example_platform_user(role: PlatformRole = PlatformRole.ADMIN) -> UUID:
    """Create an @example.com auth.users + platform_users row.

    No user_roles grant is written — callers that want one go through
    ``grant_platform_role``. Returns the new user's id.
    """
    uid = uuid4()
    email = f"x-{uid.hex[:8]}@example.com"
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await priv.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, :r, true)"
            ),
            {"id": str(uid), "e": email, "r": role.value},
        )
        await priv.commit()
    return uid


async def _cleanup_user(user_id: UUID) -> None:
    """Best-effort FK-safe teardown of an @example.com user we created."""
    async with SessionLocal() as priv:
        await priv.execute(
            text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :u"),
            {"u": str(user_id)},
        )
        await priv.execute(
            text("DELETE FROM user_roles WHERE auth_user_id = :u OR granted_by = :u"),
            {"u": str(user_id)},
        )
        await priv.execute(text("DELETE FROM platform_users WHERE id = :u"), {"u": str(user_id)})
        await priv.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(user_id)})
        await priv.commit()


async def _cleanup_role(role_id: UUID) -> None:
    """Teardown for a non-system role created by a test."""
    async with SessionLocal() as priv:
        await priv.execute(
            text("DELETE FROM rbac_audit_log WHERE target_id = :id"),
            {"id": str(role_id)},
        )
        await priv.execute(text("DELETE FROM user_roles WHERE role_id = :id"), {"id": str(role_id)})
        await priv.execute(
            text("DELETE FROM role_permissions WHERE role_id = :id"), {"id": str(role_id)}
        )
        await priv.execute(
            text("DELETE FROM roles WHERE id = :id AND NOT is_system"), {"id": str(role_id)}
        )
        await priv.commit()


async def _platform_role_id(db: AsyncSession, key: str) -> UUID:
    rid = (
        await db.execute(
            text(
                "SELECT id FROM roles WHERE scope='platform' "
                "AND workspace_id IS NULL AND key=:k AND is_system"
            ),
            {"k": key},
        )
    ).scalar_one()
    return UUID(str(rid))


async def _audit_count_for_grant(db: AsyncSession, *, grant_id: UUID, action: str) -> int:
    return int(
        (
            await db.execute(
                text(
                    "SELECT count(*) FROM rbac_audit_log " "WHERE target_id = :id AND action = :a"
                ),
                {"id": str(grant_id), "a": action},
            )
        ).scalar_one()
    )


# --- grant -----------------------------------------------------------------


async def test_grant_happy_path(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    target_id = await _create_example_platform_user()
    try:
        admin_role_id = await _platform_role_id(db_session, "admin")
        result = await grant_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            target_user_id=target_id,
            role_id=admin_role_id,
        )
        await db_session.commit()
        assert result["role_key"] == "admin"
        assert UUID(str(result["auth_user_id"])) == target_id
        assert UUID(str(result["role_id"])) == admin_role_id
        grant_id = UUID(str(result["id"]))
        assert (
            await _audit_count_for_grant(
                db_session, grant_id=grant_id, action="platform_role.grant"
            )
            == 1
        )
    finally:
        await _cleanup_user(target_id)


async def test_grant_is_idempotent(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    target_id = await _create_example_platform_user()
    try:
        admin_role_id = await _platform_role_id(db_session, "admin")
        first = await grant_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            target_user_id=target_id,
            role_id=admin_role_id,
        )
        await db_session.commit()
        second = await grant_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            target_user_id=target_id,
            role_id=admin_role_id,
        )
        await db_session.commit()
        # Same grant id (ON CONFLICT DO NOTHING + load-existing).
        assert UUID(str(first["id"])) == UUID(str(second["id"]))
    finally:
        await _cleanup_user(target_id)


async def test_grant_raises_platform_user_not_found(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    admin_role_id = await _platform_role_id(db_session, "admin")
    with pytest.raises(PlatformUserNotFoundError):
        await grant_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            target_user_id=uuid4(),
            role_id=admin_role_id,
        )
    await db_session.rollback()


async def test_grant_raises_role_not_found(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    target_id = await _create_example_platform_user()
    try:
        with pytest.raises(RoleNotFoundError):
            await grant_platform_role(
                db_session,
                actor_id=existing_super_admin.id,
                target_user_id=target_id,
                role_id=uuid4(),
            )
        await db_session.rollback()
    finally:
        await _cleanup_user(target_id)


async def test_grant_raises_scope_mismatch_on_workspace_role(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    """Pass a workspace-scope role id to the platform grant endpoint."""
    target_id = await _create_example_platform_user()
    tid, ws_role_id = uuid4(), uuid4()
    try:
        async with SessionLocal() as priv:
            await priv.execute(
                text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:id)"),
                {
                    "t": str(tid),
                    "s": f"xt-{tid.hex[:8]}",
                    "n": "P4-C1 scope probe",
                    "id": str(target_id),
                },
            )
            await priv.execute(
                text(
                    "INSERT INTO roles "
                    "(id, scope, workspace_id, key, name, description, is_system) "
                    "VALUES (:rid, 'workspace', :t, :k, 'Probe', '', false)"
                ),
                {"rid": str(ws_role_id), "t": str(tid), "k": f"probe_{tid.hex[:6]}"},
            )
            await priv.commit()

        with pytest.raises(RoleScopeMismatchError):
            await grant_platform_role(
                db_session,
                actor_id=existing_super_admin.id,
                target_user_id=target_id,
                role_id=ws_role_id,
            )
        await db_session.rollback()
    finally:
        await _cleanup_role(ws_role_id)
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tid)})
            await priv.commit()
        await _cleanup_user(target_id)


async def test_grant_raises_privilege_escalation(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    """Actor with no platform perms tries to grant the platform 'admin' role.

    The service pre-check should raise PrivilegeEscalationError BEFORE the DB
    trigger fires. The actor (a fresh @example.com platform user) has no
    user_roles grant, so they hold zero perms.
    """
    actor_id = await _create_example_platform_user()
    target_id = await _create_example_platform_user()
    try:
        admin_role_id = await _platform_role_id(db_session, "admin")
        with pytest.raises(PrivilegeEscalationError) as exc_info:
            await grant_platform_role(
                db_session,
                actor_id=actor_id,
                target_user_id=target_id,
                role_id=admin_role_id,
            )
        await db_session.rollback()
        assert exc_info.value.missing_perm_key  # non-empty
    finally:
        await _cleanup_user(target_id)
        await _cleanup_user(actor_id)


async def test_grant_raises_single_super_admin(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    """Granting super_admin when one already exists must raise — and must do
    so BEFORE INSERT (so the DB partial unique index is never hit)."""
    target_id = await _create_example_platform_user()
    try:
        sa_role_id = await _platform_role_id(db_session, "super_admin")
        with pytest.raises(SingleSuperAdminError):
            await grant_platform_role(
                db_session,
                actor_id=existing_super_admin.id,
                target_user_id=target_id,
                role_id=sa_role_id,
            )
        await db_session.rollback()
    finally:
        await _cleanup_user(target_id)


# --- revoke ----------------------------------------------------------------


async def test_revoke_happy_path(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    target_id = await _create_example_platform_user()
    try:
        admin_role_id = await _platform_role_id(db_session, "admin")
        granted = await grant_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            target_user_id=target_id,
            role_id=admin_role_id,
        )
        await db_session.commit()
        grant_id = UUID(str(granted["id"]))

        await revoke_platform_role_grant(
            db_session,
            actor_id=existing_super_admin.id,
            user_id=target_id,
            grant_id=grant_id,
        )
        await db_session.commit()

        gone = (
            await db_session.execute(
                text("SELECT count(*) FROM user_roles WHERE id = :id"),
                {"id": str(grant_id)},
            )
        ).scalar_one()
        assert int(gone) == 0
        assert (
            await _audit_count_for_grant(
                db_session, grant_id=grant_id, action="platform_role.revoke"
            )
            == 1
        )
    finally:
        await _cleanup_user(target_id)


async def test_revoke_raises_grant_not_found(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    with pytest.raises(GrantNotFoundError):
        await revoke_platform_role_grant(
            db_session,
            actor_id=existing_super_admin.id,
            user_id=existing_super_admin.id,
            grant_id=uuid4(),
        )
    await db_session.rollback()


async def test_revoke_raises_privilege_escalation(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    """A non-super_admin actor tries to revoke the real super_admin's grant.

    Setup: a fresh @example.com actor (holds zero perms) attempts to revoke
    the real operator's super_admin grant. Must raise PrivilegeEscalationError;
    the operator's grant MUST be untouched after the test.
    """
    actor_id = await _create_example_platform_user()
    sa_grant_id = UUID(
        str(
            (
                await db_session.execute(
                    text(
                        "SELECT ur.id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                        "WHERE r.scope='platform' AND r.workspace_id IS NULL "
                        "AND r.key='super_admin' AND r.is_system "
                        "AND ur.auth_user_id = :sa"
                    ),
                    {"sa": str(existing_super_admin.id)},
                )
            ).scalar_one()
        )
    )
    try:
        with pytest.raises(PrivilegeEscalationError):
            await revoke_platform_role_grant(
                db_session,
                actor_id=actor_id,
                user_id=existing_super_admin.id,
                grant_id=sa_grant_id,
            )
        await db_session.rollback()

        # Belt-and-suspenders: the operator's grant is still present.
        still_there = (
            await db_session.execute(
                text("SELECT count(*) FROM user_roles WHERE id = :id"),
                {"id": str(sa_grant_id)},
            )
        ).scalar_one()
        assert int(still_there) == 1
    finally:
        await _cleanup_user(actor_id)


# --- list ------------------------------------------------------------------


async def test_list_platform_role_grants_paginates(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    """Grant two roles to a fresh user, list with limit=1, walk the cursor."""
    target_id = await _create_example_platform_user()
    custom_role_id: UUID | None = None
    try:
        # Grant the system 'admin' role.
        admin_role_id = await _platform_role_id(db_session, "admin")
        await grant_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            target_user_id=target_id,
            role_id=admin_role_id,
        )
        await db_session.commit()

        # Create + grant a custom platform role.
        async with SessionLocal() as priv:
            cr_id = uuid4()
            await priv.execute(
                text(
                    "INSERT INTO roles "
                    "(id, scope, workspace_id, key, name, description, is_system, created_by) "
                    "VALUES (:id, 'platform', NULL, :k, 'Custom', '', false, :cb)"
                ),
                {
                    "id": str(cr_id),
                    "k": f"test_role_{uuid4().hex[:8]}",
                    "cb": str(existing_super_admin.id),
                },
            )
            await priv.commit()
            custom_role_id = cr_id
        # No perms on the custom role => actor trivially holds them all =>
        # priv-escalation check passes.
        await grant_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            target_user_id=target_id,
            role_id=custom_role_id,
        )
        await db_session.commit()

        # Walk the cursor: limit=1 ⇒ two pages.
        page1, cursor1 = await list_platform_role_grants(db_session, user_id=target_id, limit=1)
        assert len(page1) == 1
        assert cursor1 is not None
        from xtrusio_api.core.pagination import decode_cursor

        page2, cursor2 = await list_platform_role_grants(
            db_session, user_id=target_id, cursor=decode_cursor(cursor1), limit=1
        )
        assert len(page2) == 1
        assert cursor2 is None
        # Distinct rows across pages.
        assert UUID(str(page1[0]["id"])) != UUID(str(page2[0]["id"]))
        # Both should be platform-scope grants for this user.
        keys = {page1[0]["role_key"], page2[0]["role_key"]}
        assert "admin" in keys
    finally:
        if custom_role_id is not None:
            await _cleanup_role(custom_role_id)
        await _cleanup_user(target_id)
