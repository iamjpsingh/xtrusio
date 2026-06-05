"""Service-layer tests for platform-role CRUD.

Actor for every test is the real ``existing_super_admin`` (read-only fixture;
per the test-data hygiene rule we NEVER create a super_admin in tests). Because
the actor is the real operator (NOT @example.com), ``_cleanup.py`` cannot
sweep custom roles created here: each test must clean up its own seeds in a
``try/finally`` block.

Role keys follow the ``test_<hex>`` convention so a curious operator can grep
them, and so an aborted test leaves rows clearly identifiable as test debris.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser
from xtrusio_api.services.platform_roles import (
    PrivilegeEscalationError,
    RoleKeyTakenError,
    RoleNotFoundError,
    ScopeMismatchError,
    SystemRoleImmutableError,
    UnknownPermissionError,
    create_platform_role,
    delete_platform_role,
    get_platform_role,
    list_platform_roles,
    update_platform_role,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


# --- helpers ---------------------------------------------------------------


async def _cleanup_role(db: AsyncSession, role_id: UUID) -> None:
    """Best-effort teardown for a custom role created by a test."""
    await db.execute(
        text("DELETE FROM rbac_audit_log WHERE target_id = :id"),
        {"id": str(role_id)},
    )
    # user_roles + role_permissions cascade from roles, but be explicit so a
    # half-failed test can't leave grants behind.
    await db.execute(
        text("DELETE FROM user_roles WHERE role_id = :id"),
        {"id": str(role_id)},
    )
    await db.execute(
        text("DELETE FROM role_permissions WHERE role_id = :id"),
        {"id": str(role_id)},
    )
    await db.execute(
        text("DELETE FROM roles WHERE id = :id AND NOT is_system"),
        {"id": str(role_id)},
    )
    await db.commit()


async def _audit_count(db: AsyncSession, *, role_id: UUID, action: str) -> int:
    return int(
        (
            await db.execute(
                text(
                    "SELECT count(*) FROM rbac_audit_log " "WHERE target_id = :id AND action = :a"
                ),
                {"id": str(role_id), "a": action},
            )
        ).scalar_one()
    )


# --- create ----------------------------------------------------------------


async def test_create_platform_role_happy_path(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    role_key = f"test_role_{uuid4().hex[:8]}"
    role_id: UUID | None = None
    try:
        result = await create_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            key=role_key,
            name="Test Role",
            description="created by test",
            permission_keys=["platform.users.read", "platform.clients.read"],
        )
        await db_session.commit()
        role_id = UUID(str(result["id"]))
        assert result["is_system"] is False
        assert result["key"] == role_key
        assert result["name"] == "Test Role"
        assert result["description"] == "created by test"
        assert result["scope"] == "platform"
        assert result["workspace_id"] is None
        assert list(result["permission_keys"]) == [
            "platform.clients.read",
            "platform.users.read",
        ]
        assert await _audit_count(db_session, role_id=role_id, action="platform_role.create") == 1
    finally:
        if role_id is not None:
            await _cleanup_role(db_session, role_id)


async def test_create_raises_role_key_taken(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    role_key = f"test_role_{uuid4().hex[:8]}"
    role_id: UUID | None = None
    try:
        first = await create_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            key=role_key,
            name="First",
            description=None,
            permission_keys=[],
        )
        await db_session.commit()
        role_id = UUID(str(first["id"]))
        with pytest.raises(RoleKeyTakenError):
            await create_platform_role(
                db_session,
                actor_id=existing_super_admin.id,
                key=role_key,
                name="Second",
                description=None,
                permission_keys=[],
            )
        # Friendly-first check happens before INSERT, so no rollback needed
        # to keep the session usable — but tests should not assume that.
        await db_session.rollback()
    finally:
        if role_id is not None:
            await _cleanup_role(db_session, role_id)


async def test_create_raises_unknown_permission(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    role_key = f"test_role_{uuid4().hex[:8]}"
    with pytest.raises(UnknownPermissionError):
        await create_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            key=role_key,
            name="Bad",
            description=None,
            permission_keys=["nonexistent.fake.key"],
        )
    await db_session.rollback()


async def test_create_raises_scope_mismatch_on_workspace_key(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    role_key = f"test_role_{uuid4().hex[:8]}"
    with pytest.raises(ScopeMismatchError):
        await create_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            key=role_key,
            name="Bad",
            description=None,
            permission_keys=["workspace.members.invite"],
        )
    await db_session.rollback()


# --- list ------------------------------------------------------------------


async def test_list_paginates_and_includes_system_roles(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    seeded: list[UUID] = []
    try:
        for i in range(2):
            r = await create_platform_role(
                db_session,
                actor_id=existing_super_admin.id,
                key=f"test_role_{uuid4().hex[:8]}",
                name=f"Pager {i}",
                description=None,
                permission_keys=[],
            )
            await db_session.commit()
            seeded.append(UUID(str(r["id"])))

        # Walk every page; collect all keys.
        all_keys: list[str] = []
        cursor: str | None = None
        # Sanity guard: don't loop forever in the unlikely case of a bug.
        for _ in range(20):
            from xtrusio_api.core.pagination import decode_cursor

            decoded = decode_cursor(cursor) if cursor else None
            page, next_cursor = await list_platform_roles(db_session, cursor=decoded, limit=2)
            all_keys.extend(str(r["key"]) for r in page)
            if next_cursor is None:
                break
            cursor = next_cursor

        # First page request with limit=2 must yield exactly 2 and a cursor
        # (the DB has at least super_admin + admin + our 2 seeded = 4 roles).
        first_page, first_next = await list_platform_roles(db_session, limit=2)
        assert len(first_page) == 2
        assert first_next is not None

        # System roles are present.
        assert "super_admin" in all_keys
        assert "admin" in all_keys
        # Seeded custom roles are present.
        for rid in seeded:
            row = await get_platform_role(db_session, role_id=rid)
            assert row["key"] in all_keys
    finally:
        for rid in seeded:
            await _cleanup_role(db_session, rid)


# --- get -------------------------------------------------------------------


async def test_get_happy(db_session: AsyncSession, existing_super_admin: PlatformUser) -> None:
    role_id: UUID | None = None
    try:
        r = await create_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            key=f"test_role_{uuid4().hex[:8]}",
            name="Get me",
            description=None,
            permission_keys=["platform.audit.read"],
        )
        await db_session.commit()
        role_id = UUID(str(r["id"]))
        row = await get_platform_role(db_session, role_id=role_id)
        assert row["id"] == role_id or UUID(str(row["id"])) == role_id
        assert row["scope"] == "platform"
        assert list(row["permission_keys"]) == ["platform.audit.read"]
    finally:
        if role_id is not None:
            await _cleanup_role(db_session, role_id)


async def test_get_missing_raises(db_session: AsyncSession) -> None:
    with pytest.raises(RoleNotFoundError):
        await get_platform_role(db_session, role_id=uuid4())


async def test_get_workspace_role_id_raises(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    """Cross-scope isolation: a workspace role id must not resolve as a platform role.

    Seeds an ephemeral @example.com user + tenant + a workspace-scope role so
    the test is deterministic regardless of what the DB happens to contain.
    Teardown is FK-safe via ``_cleanup.py`` (the user is @example.com).
    """
    uid, tid = uuid4(), uuid4()
    email = f"x-{uid.hex[:8]}@example.com"
    ws_role_id = uuid4()
    try:
        await db_session.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await db_session.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:id)"),
            {
                "t": str(tid),
                "s": f"xt-{tid.hex[:8]}",
                "n": "P4-B2 scope probe",
                "id": str(uid),
            },
        )
        await db_session.execute(
            text(
                "INSERT INTO roles (id, scope, workspace_id, key, name, description, is_system) "
                "VALUES (:rid, 'workspace', :t, :k, 'Probe', '', false)"
            ),
            {"rid": str(ws_role_id), "t": str(tid), "k": f"probe_{uid.hex[:6]}"},
        )
        await db_session.commit()

        with pytest.raises(RoleNotFoundError):
            await get_platform_role(db_session, role_id=ws_role_id)
    finally:
        await db_session.execute(text("DELETE FROM roles WHERE id = :id"), {"id": str(ws_role_id)})
        await db_session.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tid)})
        await db_session.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(uid)})
        await db_session.commit()


# --- update ----------------------------------------------------------------


async def test_update_happy(db_session: AsyncSession, existing_super_admin: PlatformUser) -> None:
    role_id: UUID | None = None
    try:
        r = await create_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            key=f"test_role_{uuid4().hex[:8]}",
            name="Before",
            description="desc-before",
            permission_keys=["platform.users.read"],
        )
        await db_session.commit()
        role_id = UUID(str(r["id"]))
        updated = await update_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            role_id=role_id,
            name="After",
            description="desc-after",
            permission_keys=["platform.users.read", "platform.users.invite"],
        )
        await db_session.commit()
        assert updated["name"] == "After"
        assert updated["description"] == "desc-after"
        assert list(updated["permission_keys"]) == [
            "platform.users.invite",
            "platform.users.read",
        ]
        assert await _audit_count(db_session, role_id=role_id, action="platform_role.update") == 1
    finally:
        if role_id is not None:
            await _cleanup_role(db_session, role_id)


async def test_update_system_role_raises(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    sa_id = (
        await db_session.execute(
            text(
                "SELECT id FROM roles WHERE scope='platform' "
                "AND workspace_id IS NULL AND key='super_admin' AND is_system"
            )
        )
    ).scalar_one()
    with pytest.raises(SystemRoleImmutableError):
        await update_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            role_id=UUID(str(sa_id)),
            name="hacked",
            description=None,
            permission_keys=None,
        )
    await db_session.rollback()


# --- delete ----------------------------------------------------------------


async def test_delete_happy(db_session: AsyncSession, existing_super_admin: PlatformUser) -> None:
    r = await create_platform_role(
        db_session,
        actor_id=existing_super_admin.id,
        key=f"test_role_{uuid4().hex[:8]}",
        name="Doomed",
        description=None,
        permission_keys=["platform.users.read"],
    )
    await db_session.commit()
    role_id = UUID(str(r["id"]))
    try:
        await delete_platform_role(db_session, actor_id=existing_super_admin.id, role_id=role_id)
        await db_session.commit()
        with pytest.raises(RoleNotFoundError):
            await get_platform_role(db_session, role_id=role_id)
        assert await _audit_count(db_session, role_id=role_id, action="platform_role.delete") == 1
    finally:
        # The role itself is already gone; clean up the audit row + (defensively)
        # anything else.
        await _cleanup_role(db_session, role_id)


async def test_delete_system_role_raises(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    sa_id = (
        await db_session.execute(
            text(
                "SELECT id FROM roles WHERE scope='platform' "
                "AND workspace_id IS NULL AND key='super_admin' AND is_system"
            )
        )
    ).scalar_one()
    with pytest.raises(SystemRoleImmutableError):
        await delete_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            role_id=UUID(str(sa_id)),
        )
    await db_session.rollback()


# --- privilege-escalation guard (role-definition path) ---------------------
# A delegate holding ONLY `platform.roles.manage` (so the route gate passes)
# must NOT be able to mint or edit a role carrying perms they don't hold —
# closing the role-definition escalation hole (the DB trigger only fires on
# user_roles, never role_permissions).


async def _seed_delegate_with_only_roles_manage(db: AsyncSession) -> tuple[UUID, UUID]:
    """Create an @example.com platform user holding ONLY `platform.roles.manage`
    via a custom role, granted with the priv-escalation trigger bypassed (this
    is fixture setup, not an exercise of the grant path). Returns
    (actor_id, custom_role_id) — both swept by `_cleanup.py` (@example.com).
    """
    actor_id = uuid4()
    email = f"pesc-def-{actor_id.hex[:8]}@example.com"
    role_id = uuid4()
    role_key = f"test_role_{role_id.hex[:8]}"
    await db.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
            "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
            "'authenticated',:e,'',now(),now(),now())"
        ),
        {"id": str(actor_id), "e": email},
    )
    await db.execute(
        text("INSERT INTO platform_users (id, email, role, is_active) VALUES (:id,:e,:r,true)"),
        {"id": str(actor_id), "e": email, "r": PlatformRole.EDITOR.value},
    )
    await db.execute(
        text(
            "INSERT INTO roles (id, scope, workspace_id, key, name, description, is_system) "
            "VALUES (:rid,'platform',NULL,:k,'PEsc delegate','',false)"
        ),
        {"rid": str(role_id), "k": role_key},
    )
    await db.execute(
        text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT :rid, id FROM permissions WHERE key = 'platform.roles.manage'"
        ),
        {"rid": str(role_id)},
    )
    await db.execute(
        text(
            "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
            "VALUES (:u, :r, NULL, NULL)"
        ),
        {"u": str(actor_id), "r": str(role_id)},
    )
    await db.commit()
    return actor_id, role_id


async def test_create_rejects_perm_actor_lacks(db_session: AsyncSession) -> None:
    """EXPLOIT (now closed): an actor with only `platform.roles.manage` cannot
    create a role containing `platform.clients.manage`."""
    actor_id, delegate_role_id = await _seed_delegate_with_only_roles_manage(db_session)
    minted_id: UUID | None = None
    try:
        with pytest.raises(PrivilegeEscalationError):
            r = await create_platform_role(
                db_session,
                actor_id=actor_id,
                key=f"test_role_{uuid4().hex[:8]}",
                name="escalation attempt",
                description=None,
                permission_keys=["platform.clients.manage"],
            )
            minted_id = UUID(str(r["id"]))  # pragma: no cover — must not be reached
        await db_session.rollback()
    finally:
        if minted_id is not None:
            await _cleanup_role(db_session, minted_id)
        await _cleanup_role(db_session, delegate_role_id)


async def test_update_rejects_adding_perm_actor_lacks(db_session: AsyncSession) -> None:
    """EXPLOIT (now closed): the delegate cannot PATCH an existing custom role
    to ADD `platform.clients.manage` (a perm they don't hold). Evaluates the
    resulting set, not the delta."""
    actor_id, delegate_role_id = await _seed_delegate_with_only_roles_manage(db_session)
    target_id: UUID | None = None
    try:
        # Delegate legitimately creates a role with only a perm they hold.
        created = await create_platform_role(
            db_session,
            actor_id=actor_id,
            key=f"test_role_{uuid4().hex[:8]}",
            name="seed",
            description=None,
            permission_keys=["platform.roles.manage"],
        )
        await db_session.commit()
        target_id = UUID(str(created["id"]))
        with pytest.raises(PrivilegeEscalationError):
            await update_platform_role(
                db_session,
                actor_id=actor_id,
                role_id=target_id,
                name=None,
                description=None,
                permission_keys=["platform.roles.manage", "platform.clients.manage"],
            )
        await db_session.rollback()
    finally:
        if target_id is not None:
            await _cleanup_role(db_session, target_id)
        await _cleanup_role(db_session, delegate_role_id)


async def test_create_allows_perm_actor_holds(db_session: AsyncSession) -> None:
    """POSITIVE: the delegate CAN create a role containing exactly the perm they
    hold (`platform.roles.manage`)."""
    actor_id, delegate_role_id = await _seed_delegate_with_only_roles_manage(db_session)
    minted_id: UUID | None = None
    try:
        r = await create_platform_role(
            db_session,
            actor_id=actor_id,
            key=f"test_role_{uuid4().hex[:8]}",
            name="allowed",
            description=None,
            permission_keys=["platform.roles.manage"],
        )
        await db_session.commit()
        minted_id = UUID(str(r["id"]))
        assert list(r["permission_keys"]) == ["platform.roles.manage"]
    finally:
        if minted_id is not None:
            await _cleanup_role(db_session, minted_id)
        await _cleanup_role(db_session, delegate_role_id)


async def test_update_name_only_does_not_trip_guard(db_session: AsyncSession) -> None:
    """POSITIVE: a name/description-only edit (permission_keys=None) never trips
    the priv-escalation guard, even for an under-privileged delegate."""
    actor_id, delegate_role_id = await _seed_delegate_with_only_roles_manage(db_session)
    target_id: UUID | None = None
    try:
        created = await create_platform_role(
            db_session,
            actor_id=actor_id,
            key=f"test_role_{uuid4().hex[:8]}",
            name="before",
            description=None,
            permission_keys=["platform.roles.manage"],
        )
        await db_session.commit()
        target_id = UUID(str(created["id"]))
        updated = await update_platform_role(
            db_session,
            actor_id=actor_id,
            role_id=target_id,
            name="after",
            description="renamed",
            permission_keys=None,
        )
        await db_session.commit()
        assert updated["name"] == "after"
        assert list(updated["permission_keys"]) == ["platform.roles.manage"]
    finally:
        if target_id is not None:
            await _cleanup_role(db_session, target_id)
        await _cleanup_role(db_session, delegate_role_id)


async def test_super_admin_can_create_any_perm(
    db_session: AsyncSession, existing_super_admin: PlatformUser
) -> None:
    """POSITIVE: super_admin holds ALL platform perms, so the guard passes
    trivially for the full platform permission set."""
    from xtrusio_api.rbac.catalog import CATALOG

    all_platform = [p.key for p in CATALOG if p.scope == "platform"]
    role_id: UUID | None = None
    try:
        r = await create_platform_role(
            db_session,
            actor_id=existing_super_admin.id,
            key=f"test_role_{uuid4().hex[:8]}",
            name="all perms",
            description=None,
            permission_keys=all_platform,
        )
        await db_session.commit()
        role_id = UUID(str(r["id"]))
        assert sorted(r["permission_keys"]) == sorted(all_platform)
    finally:
        if role_id is not None:
            await _cleanup_role(db_session, role_id)
