"""Tests for /api/platform/users/{user_id}/roles grant/revoke/list endpoints.

Test-data hygiene: every helper uses the @example.com convention so the
session-scoped purge in conftest sweeps anything a test forgets to clean.
We never create a super_admin — `existing_super_admin` is the read-only
operator row. Custom roles created here ARE swept by `_cleanup.py` because
they're linked to ephemeral @example.com creators in the priv-escalation
test, but tests still clean up their own rows for tidy isolation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


# --- helpers ---------------------------------------------------------------


async def _create_example_platform_user(role: PlatformRole = PlatformRole.EDITOR) -> UUID:
    """Create an @example.com auth.users + platform_users row (no grants)."""
    uid = uuid4()
    email = f"prg-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
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
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, :r, true)"
            ),
            {"id": str(uid), "e": email, "r": role.value},
        )
        await s.commit()
    return uid


async def _cleanup_user(user_id: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :u"),
            {"u": str(user_id)},
        )
        await s.execute(
            text("DELETE FROM user_roles WHERE auth_user_id = :u OR granted_by = :u"),
            {"u": str(user_id)},
        )
        await s.execute(text("DELETE FROM platform_users WHERE id = :u"), {"u": str(user_id)})
        await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(user_id)})
        await s.commit()


async def _cleanup_role(role_id: UUID) -> None:
    """Teardown for a custom (non-system) role created by a test."""
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE target_id = :id"),
            {"id": str(role_id)},
        )
        await s.execute(text("DELETE FROM user_roles WHERE role_id = :id"), {"id": str(role_id)})
        await s.execute(
            text("DELETE FROM role_permissions WHERE role_id = :id"), {"id": str(role_id)}
        )
        await s.execute(
            text("DELETE FROM roles WHERE id = :id AND NOT is_system"), {"id": str(role_id)}
        )
        await s.commit()


async def _cleanup_grant(grant_id: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE target_id = :id"),
            {"id": str(grant_id)},
        )
        await s.execute(text("DELETE FROM user_roles WHERE id = :id"), {"id": str(grant_id)})
        await s.commit()


async def _platform_role_id(key: str) -> UUID:
    async with SessionLocal() as s:
        rid = (
            await s.execute(
                text(
                    "SELECT id FROM roles WHERE scope='platform' "
                    "AND workspace_id IS NULL AND key=:k AND is_system"
                ),
                {"k": key},
            )
        ).scalar_one()
        return UUID(str(rid))


async def _seed_admin_grant(user_id: UUID) -> UUID:
    """Give `user_id` the platform `admin` system role via a system-level
    seed (granted_by = NULL so the priv-escalation trigger doesn't fire).
    Returns the grant id for cleanup.
    """
    admin_role_id = await _platform_role_id("admin")
    grant_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO user_roles (id, auth_user_id, role_id, workspace_id, granted_by) "
                "VALUES (:id, :u, :r, NULL, NULL)"
            ),
            {"id": str(grant_id), "u": str(user_id), "r": str(admin_role_id)},
        )
        await s.commit()
    return grant_id


async def _create_custom_platform_role(
    *, creator_id: UUID, permission_keys: list[str] | None = None
) -> UUID:
    """Create a custom platform-scope role with the given permission keys."""
    role_id = uuid4()
    key = f"prg_custom_{role_id.hex[:8]}"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO roles "
                "(id, scope, workspace_id, key, name, description, is_system, created_by) "
                "VALUES (:id, 'platform', NULL, :k, 'Custom', '', false, :cb)"
            ),
            {"id": str(role_id), "k": key, "cb": str(creator_id)},
        )
        for pk in permission_keys or []:
            await s.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT :r, id FROM permissions WHERE key = :k"
                ),
                {"r": str(role_id), "k": pk},
            )
        await s.commit()
    return role_id


async def _create_workspace_role(*, creator_id: UUID) -> tuple[UUID, UUID]:
    """Create a workspace-scope role for scope-mismatch testing. Returns
    (tenant_id, role_id) so the caller can clean both up.
    """
    tenant_id = uuid4()
    role_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:c)"),
            {
                "t": str(tenant_id),
                "s": f"prg-{tenant_id.hex[:8]}",
                "n": "PRG scope probe",
                "c": str(creator_id),
            },
        )
        await s.execute(
            text(
                "INSERT INTO roles "
                "(id, scope, workspace_id, key, name, description, is_system) "
                "VALUES (:rid, 'workspace', :t, :k, 'WS Probe', '', false)"
            ),
            {"rid": str(role_id), "t": str(tenant_id), "k": f"ws_{role_id.hex[:6]}"},
        )
        await s.commit()
    return tenant_id, role_id


async def _delete_tenant(tenant_id: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
        await s.commit()


async def _audit_count(*, grant_id: UUID, action: str) -> int:
    async with SessionLocal() as s:
        return int(
            (
                await s.execute(
                    text(
                        "SELECT count(*) FROM rbac_audit_log "
                        "WHERE target_id = :id AND action = :a"
                    ),
                    {"id": str(grant_id), "a": action},
                )
            ).scalar_one()
        )


@pytest_asyncio.fixture
async def target_user() -> AsyncIterator[UUID]:
    """Fresh @example.com platform user, cleaned in teardown."""
    uid = await _create_example_platform_user()
    try:
        yield uid
    finally:
        await _cleanup_user(uid)


@pytest_asyncio.fixture
async def unprivileged_user() -> AsyncIterator[PlatformUser]:
    """Platform user with zero perms (no grants). Used for 403 tests."""
    uid = uuid4()
    email = f"prg-noperm-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "email": email, "e": email},
        )
        pu = PlatformUser(id=uid, email=email, role=PlatformRole.EDITOR, is_active=True)
        s.add(pu)
        await s.commit()
        await s.refresh(pu)
    try:
        yield pu
    finally:
        await _cleanup_user(uid)


# --- auth / authz gates ----------------------------------------------------


async def test_list_requires_auth(http_client: AsyncClient, target_user: UUID) -> None:
    res = await http_client.get(f"/api/platform/users/{target_user}/roles")
    assert res.status_code == 401


async def test_post_requires_auth(http_client: AsyncClient, target_user: UUID) -> None:
    res = await http_client.post(
        f"/api/platform/users/{target_user}/roles", json={"role_id": str(uuid4())}
    )
    assert res.status_code == 401


async def test_delete_requires_auth(http_client: AsyncClient, target_user: UUID) -> None:
    res = await http_client.delete(f"/api/platform/users/{target_user}/roles/{uuid4()}")
    assert res.status_code == 401


async def test_list_403_for_unprivileged(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
    target_user: UUID,
) -> None:
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.get(
        f"/api/platform/users/{target_user}/roles",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_post_403_for_unprivileged(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
    target_user: UUID,
) -> None:
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.post(
        f"/api/platform/users/{target_user}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(uuid4())},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


# --- POST happy + errors ---------------------------------------------------


async def test_post_201_happy_path(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    target_user: UUID,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    admin_role_id = await _platform_role_id("admin")
    grant_id: UUID | None = None
    try:
        res = await http_client.post(
            f"/api/platform/users/{target_user}/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"role_id": str(admin_role_id)},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert UUID(body["auth_user_id"]) == target_user
        assert UUID(body["role_id"]) == admin_role_id
        assert body["role_key"] == "admin"
        assert UUID(body["granted_by"]) == existing_super_admin.id
        grant_id = UUID(body["id"])
        # Audit row written in the same tx.
        assert await _audit_count(grant_id=grant_id, action="platform_role.grant") == 1
    finally:
        if grant_id is not None:
            await _cleanup_grant(grant_id)


async def test_post_404_platform_user_not_found(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    admin_role_id = await _platform_role_id("admin")
    res = await http_client.post(
        f"/api/platform/users/{uuid4()}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(admin_role_id)},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "platform_user_not_found"


async def test_post_404_role_not_found(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    target_user: UUID,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.post(
        f"/api/platform/users/{target_user}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(uuid4())},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "role_not_found"


async def test_post_422_role_scope_mismatch(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    target_user: UUID,
) -> None:
    """Pass a workspace-scope role id to the platform grant endpoint."""
    tenant_id, ws_role_id = await _create_workspace_role(creator_id=existing_super_admin.id)
    try:
        token = make_jwt(sub=existing_super_admin.id)
        res = await http_client.post(
            f"/api/platform/users/{target_user}/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"role_id": str(ws_role_id)},
        )
        assert res.status_code == 422
        assert res.json()["detail"] == "role_scope_mismatch"
    finally:
        await _cleanup_role(ws_role_id)
        await _delete_tenant(tenant_id)


async def test_post_422_invalid_role_id_not_uuid(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    target_user: UUID,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.post(
        f"/api/platform/users/{target_user}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": "not-a-uuid"},
    )
    assert res.status_code == 422


async def test_post_403_privilege_escalation(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    target_user: UUID,
    existing_super_admin: PlatformUser,
) -> None:
    """Actor holds platform `admin` (=> has `platform.users.manage` so the
    route gate passes), tries to grant a custom role containing
    `platform.roles.manage` — which `admin` does NOT hold. Service raises
    PrivilegeEscalationError => 403.
    """
    actor_id = await _create_example_platform_user()
    actor_grant_id = await _seed_admin_grant(actor_id)
    custom_role_id = await _create_custom_platform_role(
        creator_id=existing_super_admin.id,
        permission_keys=["platform.roles.manage"],
    )
    try:
        token = make_jwt(sub=actor_id)
        res = await http_client.post(
            f"/api/platform/users/{target_user}/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"role_id": str(custom_role_id)},
        )
        assert res.status_code == 403, res.text
        # PAR-A M22: response body is the bare constant — the missing perm
        # key stays server-side only (logged), never returned to the client
        # (which would leak the internal RBAC graph).
        assert res.json()["detail"] == "privilege_escalation"
    finally:
        await _cleanup_grant(actor_grant_id)
        await _cleanup_role(custom_role_id)
        await _cleanup_user(actor_id)


async def test_post_409_single_super_admin_invariant(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    target_user: UUID,
) -> None:
    """Granting super_admin when one already exists must 409."""
    token = make_jwt(sub=existing_super_admin.id)
    sa_role_id = await _platform_role_id("super_admin")
    res = await http_client.post(
        f"/api/platform/users/{target_user}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(sa_role_id)},
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "single_super_admin_invariant"


# --- DELETE -----------------------------------------------------------------


async def test_delete_204_happy_path(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    target_user: UUID,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    admin_role_id = await _platform_role_id("admin")
    # POST a grant, then DELETE it.
    post_res = await http_client.post(
        f"/api/platform/users/{target_user}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(admin_role_id)},
    )
    assert post_res.status_code == 201, post_res.text
    grant_id = UUID(post_res.json()["id"])
    try:
        del_res = await http_client.delete(
            f"/api/platform/users/{target_user}/roles/{grant_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_res.status_code == 204
        # Grant gone.
        async with SessionLocal() as s:
            gone = (
                await s.execute(
                    text("SELECT count(*) FROM user_roles WHERE id = :id"),
                    {"id": str(grant_id)},
                )
            ).scalar_one()
            assert int(gone) == 0
        assert await _audit_count(grant_id=grant_id, action="platform_role.revoke") == 1
    finally:
        await _cleanup_grant(grant_id)


async def test_delete_404_grant_not_found(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    target_user: UUID,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.delete(
        f"/api/platform/users/{target_user}/roles/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "grant_not_found"


# --- GET / pagination -------------------------------------------------------


async def test_get_cursor_pagination_roundtrip(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    target_user: UUID,
) -> None:
    """Grant two platform roles to one user, list with limit=1, walk cursor."""
    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    admin_role_id = await _platform_role_id("admin")
    custom_role_id = await _create_custom_platform_role(
        creator_id=existing_super_admin.id, permission_keys=[]
    )
    grant_ids: list[UUID] = []
    try:
        for rid in (admin_role_id, custom_role_id):
            r = await http_client.post(
                f"/api/platform/users/{target_user}/roles",
                headers=headers,
                json={"role_id": str(rid)},
            )
            assert r.status_code == 201, r.text
            grant_ids.append(UUID(r.json()["id"]))

        r1 = await http_client.get(
            f"/api/platform/users/{target_user}/roles?limit=1", headers=headers
        )
        assert r1.status_code == 200
        p1 = r1.json()
        assert len(p1["items"]) == 1
        assert p1["next_cursor"] is not None

        r2 = await http_client.get(
            f"/api/platform/users/{target_user}/roles?limit=1&cursor={p1['next_cursor']}",
            headers=headers,
        )
        assert r2.status_code == 200
        p2 = r2.json()
        assert len(p2["items"]) == 1
        assert p2["next_cursor"] is None
        # Distinct ids across pages.
        ids_seen = {p1["items"][0]["id"], p2["items"][0]["id"]}
        assert len(ids_seen) == 2
    finally:
        for gid in grant_ids:
            await _cleanup_grant(gid)
        await _cleanup_role(custom_role_id)


async def test_get_invalid_cursor_400(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    target_user: UUID,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.get(
        f"/api/platform/users/{target_user}/roles?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid cursor"
