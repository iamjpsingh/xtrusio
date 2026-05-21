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
    RoleKeyTakenError,
    RoleNotFoundError,
    ScopeMismatchError,
    UnknownPermissionError,
    create_workspace_role,
    get_workspace_role,
    list_workspace_roles,
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
