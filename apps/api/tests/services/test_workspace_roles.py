"""Service-layer tests for workspace-role CRUD.

Actor for every test is a fresh @example.com owner of an @example.com tenant.
`_cleanup.py` sweeps everything by tenant.created_by = actor_id.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.workspace_roles import (
    PrivilegeEscalationError,
    RoleKeyTakenError,
    RoleNotFoundError,
    ScopeMismatchError,
    SystemRoleImmutableError,
    UnknownPermissionError,
    create_workspace_role,
    get_workspace_role,
    list_workspace_roles,
    update_workspace_role,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_owner_workspace() -> tuple[UUID, UUID]:
    """Seed @example.com owner + tenant + tenant_memberships(owner) +
    workspace system roles via the reconciler. Returns (workspace_id, owner_id).
    """
    uid, tid = uuid4(), uuid4()
    email = f"wsr-svc-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        # System bypass — we're seeding fixture state, not exercising auth.
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
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
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"wsr-{tid.hex[:8]}", "n": "WSR tenant", "u": str(uid)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await s.commit()

    # Boot reconciler seeds workspace system roles + projects tenant_memberships
    # -> user_roles. Do the same here so the owner actually holds owner perms.
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return tid, uid


async def test_create_workspace_role_happy_path(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    role_key = f"test_wsr_{uuid4().hex[:8]}"
    result = await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=role_key,
        name="Test Workspace Role",
        description="created by test",
        permission_keys=["workspace.members.read", "workspace.settings.read"],
    )
    await db_session.commit()
    assert result["is_system"] is False
    assert result["key"] == role_key
    assert result["scope"] == "workspace"
    assert UUID(str(result["workspace_id"])) == tid
    assert list(result["permission_keys"]) == [
        "workspace.members.read",
        "workspace.settings.read",
    ]


async def test_create_raises_role_key_taken(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    role_key = f"test_wsr_{uuid4().hex[:8]}"
    await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=role_key,
        name="First",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    with pytest.raises(RoleKeyTakenError):
        await create_workspace_role(
            db_session,
            actor_id=uid,
            workspace_id=tid,
            key=role_key,
            name="Second",
            description=None,
            permission_keys=[],
        )
    await db_session.rollback()


async def test_create_raises_unknown_permission(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    with pytest.raises(UnknownPermissionError):
        await create_workspace_role(
            db_session,
            actor_id=uid,
            workspace_id=tid,
            key=f"test_wsr_{uuid4().hex[:8]}",
            name="Bad",
            description=None,
            permission_keys=["nonexistent.fake.key"],
        )
    await db_session.rollback()


async def test_create_raises_scope_mismatch_on_platform_key(
    db_session: AsyncSession,
) -> None:
    tid, uid = await _seed_owner_workspace()
    with pytest.raises(ScopeMismatchError):
        await create_workspace_role(
            db_session,
            actor_id=uid,
            workspace_id=tid,
            key=f"test_wsr_{uuid4().hex[:8]}",
            name="Bad scope",
            description=None,
            permission_keys=["platform.users.read"],
        )
    await db_session.rollback()


async def test_list_returns_system_and_custom(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    r = await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="Custom",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    page, _ = await list_workspace_roles(db_session, workspace_id=tid, limit=200)
    keys = {row["key"] for row in page}
    # System roles seeded per-workspace in `reconcile_user_roles_from_enums`.
    assert "owner" in keys
    assert "admin" in keys
    assert "editor" in keys
    assert "read_only" in keys
    assert str(r["key"]) in keys


async def test_get_workspace_role_404_cross_workspace(
    db_session: AsyncSession,
) -> None:
    """A role from workspace A must not resolve when queried under workspace B.
    Scope-isolation regression guard."""
    tid_a, uid_a = await _seed_owner_workspace()
    tid_b, _ = await _seed_owner_workspace()
    r = await create_workspace_role(
        db_session,
        actor_id=uid_a,
        workspace_id=tid_a,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="In A",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    role_id = UUID(str(r["id"]))
    # Lookup under tid_b must 404.
    with pytest.raises(RoleNotFoundError):
        await get_workspace_role(db_session, workspace_id=tid_b, role_id=role_id)
    # But succeeds under tid_a.
    found = await get_workspace_role(db_session, workspace_id=tid_a, role_id=role_id)
    assert UUID(str(found["id"])) == role_id


async def test_update_workspace_role_happy(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import update_workspace_role

    r = await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="Before",
        description="desc-before",
        permission_keys=["workspace.members.read"],
    )
    await db_session.commit()
    role_id = UUID(str(r["id"]))
    updated = await update_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        role_id=role_id,
        name="After",
        description="desc-after",
        permission_keys=["workspace.members.read", "workspace.members.invite"],
    )
    await db_session.commit()
    assert updated["name"] == "After"
    assert updated["description"] == "desc-after"
    assert list(updated["permission_keys"]) == [
        "workspace.members.invite",
        "workspace.members.read",
    ]


async def test_update_system_role_raises(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import update_workspace_role

    owner_role_id = UUID(
        str(
            (
                await db_session.execute(
                    text(
                        "SELECT id FROM roles WHERE scope='workspace' "
                        "AND workspace_id = :w AND key='owner' AND is_system"
                    ),
                    {"w": str(tid)},
                )
            ).scalar_one()
        )
    )
    with pytest.raises(SystemRoleImmutableError):
        await update_workspace_role(
            db_session,
            actor_id=uid,
            workspace_id=tid,
            role_id=owner_role_id,
            name="renamed-owner",
            description=None,
            permission_keys=None,
        )
    await db_session.rollback()


async def test_delete_workspace_role_happy(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import delete_workspace_role

    r = await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="Doomed",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    role_id = UUID(str(r["id"]))
    await delete_workspace_role(db_session, actor_id=uid, workspace_id=tid, role_id=role_id)
    await db_session.commit()
    with pytest.raises(RoleNotFoundError):
        await get_workspace_role(db_session, workspace_id=tid, role_id=role_id)


async def test_delete_system_role_raises(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import delete_workspace_role

    editor_role_id = UUID(
        str(
            (
                await db_session.execute(
                    text(
                        "SELECT id FROM roles WHERE scope='workspace' "
                        "AND workspace_id = :w AND key='editor' AND is_system"
                    ),
                    {"w": str(tid)},
                )
            ).scalar_one()
        )
    )
    with pytest.raises(SystemRoleImmutableError):
        await delete_workspace_role(
            db_session, actor_id=uid, workspace_id=tid, role_id=editor_role_id
        )
    await db_session.rollback()


async def test_update_role_from_other_workspace_404s(
    db_session: AsyncSession,
) -> None:
    """Cross-workspace scope isolation — update must 404 if role lives elsewhere."""
    tid_a, uid_a = await _seed_owner_workspace()
    tid_b, _ = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import update_workspace_role

    r = await create_workspace_role(
        db_session,
        actor_id=uid_a,
        workspace_id=tid_a,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="In A",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    role_id = UUID(str(r["id"]))
    with pytest.raises(RoleNotFoundError):
        await update_workspace_role(
            db_session,
            actor_id=uid_a,
            workspace_id=tid_b,
            role_id=role_id,
            name="hijack",
            description=None,
            permission_keys=None,
        )
    await db_session.rollback()


# --- privilege-escalation guard (role-definition path) ---------------------
# A delegate holding ONLY `workspace.roles.manage` in workspace W (so the route
# gate passes) must NOT be able to mint or edit a role carrying perms they don't
# hold (e.g. workspace.members.manage / workspace.settings.manage).


async def _seed_roles_manage_delegate(workspace_id: UUID) -> UUID:
    """Add a fresh @example.com user holding ONLY `workspace.roles.manage` in
    ``workspace_id`` via a custom role, granted with the priv-escalation trigger
    bypassed (fixture setup, not the grant path). Returns the user id; swept by
    `_cleanup.py` via the @example.com user (which cascades user_roles + the
    custom role's grant).

    Deliberately NOT a `tenant_memberships` member: ``has_workspace_perm`` reads
    ONLY ``user_roles`` + ``role_permissions`` (verified in 0007), and the
    role-CRUD path never checks membership — so the delegate's effective perms
    are EXACTLY the custom role's single perm, with no risk of the reconciler's
    enum->user_roles projection (which maps a `tenant_memberships` role to a
    system role) silently widening them. The role-definition guard is what we're
    testing, not the grant path.
    """
    uid = uuid4()
    email = f"wsr-deleg-{uid.hex[:8]}@example.com"
    role_id = uuid4()
    role_key = f"test_wsr_{role_id.hex[:8]}"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO roles (id, scope, workspace_id, key, name, description, is_system) "
                "VALUES (:rid,'workspace',:t,:k,'PEsc delegate','',false)"
            ),
            {"rid": str(role_id), "t": str(workspace_id), "k": role_key},
        )
        await s.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT :rid, id FROM permissions WHERE key = 'workspace.roles.manage'"
            ),
            {"rid": str(role_id)},
        )
        await s.execute(
            text(
                "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
                "VALUES (:u, :r, :t, NULL)"
            ),
            {"u": str(uid), "r": str(role_id), "t": str(workspace_id)},
        )
        await s.commit()
    return uid


async def test_ws_create_rejects_perm_actor_lacks(db_session: AsyncSession) -> None:
    """EXPLOIT (now closed): a delegate with only `workspace.roles.manage`
    cannot create a role containing `workspace.members.manage`."""
    tid, _owner = await _seed_owner_workspace()
    delegate_id = await _seed_roles_manage_delegate(tid)
    with pytest.raises(PrivilegeEscalationError):
        await create_workspace_role(
            db_session,
            actor_id=delegate_id,
            workspace_id=tid,
            key=f"test_wsr_{uuid4().hex[:8]}",
            name="escalation attempt",
            description=None,
            permission_keys=["workspace.members.manage"],
        )
    await db_session.rollback()


async def test_ws_update_rejects_adding_perm_actor_lacks(db_session: AsyncSession) -> None:
    """EXPLOIT (now closed): the delegate cannot PATCH a custom role to ADD
    `workspace.settings.manage`. Evaluates the resulting set, not the delta."""
    tid, _owner = await _seed_owner_workspace()
    delegate_id = await _seed_roles_manage_delegate(tid)
    created = await create_workspace_role(
        db_session,
        actor_id=delegate_id,
        workspace_id=tid,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="seed",
        description=None,
        permission_keys=["workspace.roles.manage"],
    )
    await db_session.commit()
    role_id = UUID(str(created["id"]))
    with pytest.raises(PrivilegeEscalationError):
        await update_workspace_role(
            db_session,
            actor_id=delegate_id,
            workspace_id=tid,
            role_id=role_id,
            name=None,
            description=None,
            permission_keys=["workspace.roles.manage", "workspace.settings.manage"],
        )
    await db_session.rollback()


async def test_ws_create_allows_perm_actor_holds(db_session: AsyncSession) -> None:
    """POSITIVE: the delegate CAN create a role containing exactly the perm they
    hold (`workspace.roles.manage`)."""
    tid, _owner = await _seed_owner_workspace()
    delegate_id = await _seed_roles_manage_delegate(tid)
    r = await create_workspace_role(
        db_session,
        actor_id=delegate_id,
        workspace_id=tid,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="allowed",
        description=None,
        permission_keys=["workspace.roles.manage"],
    )
    await db_session.commit()
    assert list(r["permission_keys"]) == ["workspace.roles.manage"]


async def test_ws_owner_can_create_any_perm(db_session: AsyncSession) -> None:
    """POSITIVE: a workspace owner holds ALL workspace perms, so the guard
    passes trivially for the full workspace permission set."""
    from xtrusio_api.rbac.catalog import CATALOG

    tid, owner = await _seed_owner_workspace()
    all_ws = [p.key for p in CATALOG if p.scope == "workspace"]
    r = await create_workspace_role(
        db_session,
        actor_id=owner,
        workspace_id=tid,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="all ws perms",
        description=None,
        permission_keys=all_ws,
    )
    await db_session.commit()
    assert sorted(r["permission_keys"]) == sorted(all_ws)
