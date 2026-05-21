"""Service-layer tests for workspace-role grant/revoke.

Test-data hygiene: every helper uses the @example.com convention; `_cleanup.py`
sweeps all @example.com creators (auth.users, platform_users, tenants,
tenant_memberships, user_roles, rbac_audit_log, custom non-system roles).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.workspace_role_grants import (
    GrantNotFoundError,
    MembershipNotFoundError,
    OwnerFloorError,
    PrivilegeEscalationError,
    RoleNotFoundError,
    _require_workspace_membership,
    grant_workspace_role,
    list_workspace_role_grants,
    revoke_workspace_role_grant,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_tenant_with_owner() -> tuple[UUID, UUID]:
    """Seed an @example.com auth.user + tenant + tenant_memberships (owner).
    Returns (workspace_id, owner_user_id)."""
    uid, tid = uuid4(), uuid4()
    email = f"wrg-owner-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) " "VALUES (:t,:s,:n,:u)"),
            {
                "t": str(tid),
                "s": f"wrg-{tid.hex[:8]}",
                "n": "WRG tenant",
                "u": str(uid),
            },
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await s.commit()
    return tid, uid


async def test_require_membership_passes_for_member(db_session: AsyncSession) -> None:
    tid, uid = await _seed_tenant_with_owner()
    # Should not raise.
    await _require_workspace_membership(db_session, workspace_id=tid, user_id=uid)


async def test_require_membership_raises_for_non_member(db_session: AsyncSession) -> None:
    tid, _ = await _seed_tenant_with_owner()
    with pytest.raises(MembershipNotFoundError):
        await _require_workspace_membership(db_session, workspace_id=tid, user_id=uuid4())


async def _seed_member(workspace_id: UUID, role: str = "editor") -> UUID:
    """Add a fresh @example.com user as a tenant_memberships member of the
    given workspace. Returns the user id."""
    uid = uuid4()
    email = f"wrg-member-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) " "VALUES (:t, :u, :r)"
            ),
            {"t": str(workspace_id), "u": str(uid), "r": role},
        )
        await s.commit()
    # Project to user_roles so the member actually holds the role's perms.
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return uid


async def _role_id(workspace_id: UUID, key: str, is_system: bool = True) -> UUID:
    async with SessionLocal() as s:
        rid = (
            await s.execute(
                text(
                    "SELECT id FROM roles WHERE scope='workspace' "
                    "AND workspace_id = :w AND key = :k AND is_system = :sys"
                ),
                {"w": str(workspace_id), "k": key, "sys": is_system},
            )
        ).scalar_one()
        return UUID(str(rid))


async def test_grant_happy_path(db_session: AsyncSession) -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    # Reconcile so the owner holds workspace owner perms.
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    member_id = await _seed_member(tid, "editor")
    admin_role = await _role_id(tid, "admin", is_system=True)
    result = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=member_id,
        role_id=admin_role,
    )
    await db_session.commit()
    assert result["role_key"] == "admin"
    assert UUID(str(result["auth_user_id"])) == member_id
    assert UUID(str(result["workspace_id"])) == tid


async def test_grant_404_for_non_member(db_session: AsyncSession) -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    admin_role = await _role_id(tid, "admin", is_system=True)
    with pytest.raises(MembershipNotFoundError):
        await grant_workspace_role(
            db_session,
            actor_id=owner_id,
            workspace_id=tid,
            target_user_id=uuid4(),
            role_id=admin_role,
        )
    await db_session.rollback()


async def test_grant_role_from_other_workspace_404s(db_session: AsyncSession) -> None:
    """Scope isolation — role_id from another workspace must RoleNotFoundError."""
    tid_a, owner_a = await _seed_tenant_with_owner()
    tid_b, _ = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    member_a = await _seed_member(tid_a, "editor")
    admin_role_b = await _role_id(tid_b, "admin", is_system=True)
    with pytest.raises(RoleNotFoundError):
        await grant_workspace_role(
            db_session,
            actor_id=owner_a,
            workspace_id=tid_a,
            target_user_id=member_a,
            role_id=admin_role_b,
        )
    await db_session.rollback()


async def test_grant_raises_privilege_escalation(db_session: AsyncSession) -> None:
    """An editor (no workspace.roles.manage) tries to grant the workspace
    owner role. Service raises PrivilegeEscalationError before the DB trigger
    fires."""
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    editor_id = await _seed_member(tid, "editor")
    target_id = await _seed_member(tid, "editor")
    owner_role = await _role_id(tid, "owner", is_system=True)
    with pytest.raises(PrivilegeEscalationError):
        await grant_workspace_role(
            db_session,
            actor_id=editor_id,
            workspace_id=tid,
            target_user_id=target_id,
            role_id=owner_role,
        )
    await db_session.rollback()


async def test_grant_idempotent(db_session: AsyncSession) -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    # The owner is already a member with the owner role; grant 'owner' again
    # via the API path and expect the same grant id back.
    owner_role = await _role_id(tid, "owner", is_system=True)
    a = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=owner_id,
        role_id=owner_role,
    )
    await db_session.commit()
    b = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=owner_id,
        role_id=owner_role,
    )
    await db_session.commit()
    assert UUID(str(a["id"])) == UUID(str(b["id"]))


async def test_revoke_happy_path(db_session: AsyncSession) -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    member_id = await _seed_member(tid, "editor")
    admin_role = await _role_id(tid, "admin", is_system=True)
    granted = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=member_id,
        role_id=admin_role,
    )
    await db_session.commit()
    grant_id = UUID(str(granted["id"]))
    await revoke_workspace_role_grant(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        user_id=member_id,
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


async def test_revoke_owner_floor_409_when_last_owner(
    db_session: AsyncSession,
) -> None:
    """A workspace must retain ≥1 active owner grant — revoking the last
    one MUST raise OwnerFloorError."""
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    owner_grant_id = UUID(
        str(
            (
                await db_session.execute(
                    text(
                        "SELECT ur.id FROM user_roles ur "
                        "JOIN roles r ON r.id = ur.role_id "
                        "WHERE r.scope='workspace' AND r.workspace_id = :w "
                        "AND r.key='owner' AND r.is_system "
                        "AND ur.auth_user_id = :u AND ur.workspace_id = :w"
                    ),
                    {"w": str(tid), "u": str(owner_id)},
                )
            ).scalar_one()
        )
    )
    with pytest.raises(OwnerFloorError):
        await revoke_workspace_role_grant(
            db_session,
            actor_id=owner_id,
            workspace_id=tid,
            user_id=owner_id,
            grant_id=owner_grant_id,
        )
    await db_session.rollback()


async def test_revoke_owner_204_when_two_owners(db_session: AsyncSession) -> None:
    """Multiple owners allowed: with 2 owners, revoking 1 must succeed."""
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    # Add a second member and grant them the workspace owner role explicitly
    # via the service path (priv-escalation pre-check should pass — owner_id
    # holds every workspace perm).
    second = await _seed_member(tid, "editor")
    owner_role = await _role_id(tid, "owner", is_system=True)
    g = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=second,
        role_id=owner_role,
    )
    await db_session.commit()
    grant_id = UUID(str(g["id"]))
    # Revoke the second owner — first owner remains, so the floor still holds.
    await revoke_workspace_role_grant(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        user_id=second,
        grant_id=grant_id,
    )
    await db_session.commit()


async def test_revoke_grant_from_other_workspace_404s(
    db_session: AsyncSession,
) -> None:
    """Pass a grant_id whose workspace_id != URL workspace_id => 404."""
    tid_a, owner_a = await _seed_tenant_with_owner()
    tid_b, _ = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    member_b = await _seed_member(tid_b, "editor")
    # Find member_b's editor grant in tid_b.
    grant_b_id = UUID(
        str(
            (
                await db_session.execute(
                    text(
                        "SELECT ur.id FROM user_roles ur "
                        "JOIN roles r ON r.id = ur.role_id "
                        "WHERE r.scope='workspace' AND r.workspace_id = :w "
                        "AND ur.auth_user_id = :u"
                    ),
                    {"w": str(tid_b), "u": str(member_b)},
                )
            ).scalar_one()
        )
    )
    with pytest.raises(GrantNotFoundError):
        await revoke_workspace_role_grant(
            db_session,
            actor_id=owner_a,
            workspace_id=tid_a,
            user_id=member_b,
            grant_id=grant_b_id,
        )
    await db_session.rollback()


async def test_list_grants_filtered_to_workspace(
    db_session: AsyncSession,
) -> None:
    """List returns only this workspace's grants for this user."""
    tid_a, owner_a = await _seed_tenant_with_owner()
    tid_b, _ = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    # Add owner_a as a member of tid_b too (editor), so they have grants in
    # both workspaces. Listing under tid_a must return only tid_a grants.
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'editor')"
            ),
            {"t": str(tid_b), "u": str(owner_a)},
        )
        await s.commit()
    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    rows, _ = await list_workspace_role_grants(
        db_session, workspace_id=tid_a, user_id=owner_a, limit=200
    )
    assert all(UUID(str(r["workspace_id"])) == tid_a for r in rows)
    assert len(rows) >= 1  # at least the owner grant
