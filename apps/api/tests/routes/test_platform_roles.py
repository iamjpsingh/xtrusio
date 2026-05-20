"""Tests for /api/platform/roles CRUD."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def unprivileged_user() -> AsyncIterator[PlatformUser]:
    """A provisioned platform user with NO platform-role grants — holds no
    platform permission, so `platform.roles.manage` resolves false."""
    user_id = uuid4()
    email = f"prole-noperm-{user_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(user_id), "email": email},
        )
        pu = PlatformUser(id=user_id, email=email, role=PlatformRole.EDITOR, is_active=True)
        s.add(pu)
        await s.commit()
        await s.refresh(pu)
    try:
        yield pu
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM user_roles WHERE auth_user_id = :id"), {"id": str(user_id)}
            )
            await s.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
            await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await s.commit()


async def _delete_role(role_id: str) -> None:
    """Best-effort cleanup of a custom role created during a test.

    Custom roles created by `existing_super_admin` (real owner email, not
    @example.com) are NOT swept by `_cleanup.py`, so each test must clean its
    own. Uses the bypass flag because the 0009 governance trigger rejects
    mutations from non-actor contexts — fine for teardown.
    """
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(text("DELETE FROM roles WHERE id = :id"), {"id": role_id})
        await s.commit()


# --- auth / authz gates ----------------------------------------------------


async def test_list_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/platform/roles")
    assert res.status_code == 401


async def test_list_403_for_unprivileged(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
) -> None:
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.get("/api/platform/roles", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_list_200_for_super_admin(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.get("/api/platform/roles", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    keys = {r["key"] for r in body["items"]}
    # Both seeded system roles must be present.
    assert "super_admin" in keys
    assert "admin" in keys


# --- create ---------------------------------------------------------------


async def test_create_role_201_happy(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    role_id: str | None = None
    try:
        res = await http_client.post(
            "/api/platform/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "key": "auditor_role",
                "name": "Auditor",
                "description": "Read-only auditor",
                "permission_keys": ["platform.audit.read"],
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        role_id = body["id"]
        assert body["key"] == "auditor_role"
        assert body["name"] == "Auditor"
        assert body["is_system"] is False
        assert body["permission_keys"] == ["platform.audit.read"]
    finally:
        if role_id is not None:
            await _delete_role(role_id)


async def test_create_role_409_on_duplicate_key(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    role_id: str | None = None
    try:
        a = await http_client.post(
            "/api/platform/roles",
            headers=headers,
            json={"key": "dup_role", "name": "Dup", "permission_keys": []},
        )
        assert a.status_code == 201, a.text
        role_id = a.json()["id"]
        b = await http_client.post(
            "/api/platform/roles",
            headers=headers,
            json={"key": "dup_role", "name": "Dup 2", "permission_keys": []},
        )
        assert b.status_code == 409
        assert b.json()["detail"] == "role_key_taken"
    finally:
        if role_id is not None:
            await _delete_role(role_id)


async def test_create_role_422_unknown_permission(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.post(
        "/api/platform/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key": "bogus_perm_role",
            "name": "Bogus",
            "permission_keys": ["bogus.fake.key"],
        },
    )
    assert res.status_code == 422


async def test_create_role_422_scope_mismatch(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.post(
        "/api/platform/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key": "scope_mismatch_role",
            "name": "Scope Mismatch",
            "permission_keys": ["workspace.members.invite"],
        },
    )
    assert res.status_code == 422


async def test_create_role_422_invalid_key_format(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    # Pydantic-level validation: key must match ^[a-z][a-z0-9_]*$.
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.post(
        "/api/platform/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"key": "HAS UPPER", "name": "Bad Key", "permission_keys": []},
    )
    assert res.status_code == 422


# --- get ------------------------------------------------------------------


async def test_get_role_happy_and_404(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    role_id: str | None = None
    try:
        c = await http_client.post(
            "/api/platform/roles",
            headers=headers,
            json={"key": "get_target_role", "name": "Target", "permission_keys": []},
        )
        assert c.status_code == 201, c.text
        role_id = c.json()["id"]

        g = await http_client.get(f"/api/platform/roles/{role_id}", headers=headers)
        assert g.status_code == 200
        assert g.json()["id"] == role_id
        assert g.json()["key"] == "get_target_role"

        # 404 on unknown id.
        missing = uuid4()
        g404 = await http_client.get(f"/api/platform/roles/{missing}", headers=headers)
        assert g404.status_code == 404
        assert g404.json()["detail"] == "role_not_found"
    finally:
        if role_id is not None:
            await _delete_role(role_id)


# --- patch ----------------------------------------------------------------


async def test_patch_role_422_on_system_role(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    # Find super_admin's id via the list endpoint.
    lst = await http_client.get("/api/platform/roles", headers=headers)
    assert lst.status_code == 200
    super_admin = next(r for r in lst.json()["items"] if r["key"] == "super_admin")

    res = await http_client.patch(
        f"/api/platform/roles/{super_admin['id']}",
        headers=headers,
        json={"name": "Renamed Super Admin"},
    )
    assert res.status_code == 422
    assert res.json()["detail"] == "system_role_immutable"


async def test_patch_role_happy(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    role_id: str | None = None
    try:
        c = await http_client.post(
            "/api/platform/roles",
            headers=headers,
            json={
                "key": "patch_target_role",
                "name": "Original",
                "permission_keys": ["platform.audit.read"],
            },
        )
        assert c.status_code == 201, c.text
        role_id = c.json()["id"]

        p = await http_client.patch(
            f"/api/platform/roles/{role_id}",
            headers=headers,
            json={
                "name": "Updated",
                "permission_keys": [
                    "platform.audit.read",
                    "platform.users.read",
                ],
            },
        )
        assert p.status_code == 200, p.text
        body = p.json()
        assert body["name"] == "Updated"
        assert body["permission_keys"] == [
            "platform.audit.read",
            "platform.users.read",
        ]
    finally:
        if role_id is not None:
            await _delete_role(role_id)


# --- delete ---------------------------------------------------------------


async def test_delete_role_422_on_system_role(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    lst = await http_client.get("/api/platform/roles", headers=headers)
    assert lst.status_code == 200
    admin = next(r for r in lst.json()["items"] if r["key"] == "admin")

    res = await http_client.delete(f"/api/platform/roles/{admin['id']}", headers=headers)
    assert res.status_code == 422
    assert res.json()["detail"] == "system_role_immutable"


async def test_delete_role_204_on_custom(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    c = await http_client.post(
        "/api/platform/roles",
        headers=headers,
        json={"key": "delete_target_role", "name": "ToDelete", "permission_keys": []},
    )
    assert c.status_code == 201, c.text
    role_id = c.json()["id"]

    try:
        d = await http_client.delete(f"/api/platform/roles/{role_id}", headers=headers)
        assert d.status_code == 204

        # GET should 404 now.
        g = await http_client.get(f"/api/platform/roles/{role_id}", headers=headers)
        assert g.status_code == 404
    finally:
        # In case the DELETE failed mid-test, sweep the row.
        await _delete_role(role_id)


# --- pagination -----------------------------------------------------------


async def test_list_paginates(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    created: list[str] = []
    try:
        for i in range(3):
            c = await http_client.post(
                "/api/platform/roles",
                headers=headers,
                json={
                    "key": f"page_role_{i}",
                    "name": f"Page {i}",
                    "permission_keys": [],
                },
            )
            assert c.status_code == 201, c.text
            created.append(c.json()["id"])

        r1 = await http_client.get("/api/platform/roles?limit=2", headers=headers)
        assert r1.status_code == 200
        p1 = r1.json()
        assert len(p1["items"]) == 2
        assert p1["next_cursor"] is not None

        r2 = await http_client.get(
            f"/api/platform/roles?limit=2&cursor={p1['next_cursor']}",
            headers=headers,
        )
        assert r2.status_code == 200
        p2 = r2.json()
        assert len(p2["items"]) >= 1
        ids1 = {r["id"] for r in p1["items"]}
        ids2 = {r["id"] for r in p2["items"]}
        assert ids1.isdisjoint(ids2)
    finally:
        for rid in created:
            await _delete_role(rid)


async def test_list_rejects_invalid_cursor(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.get(
        "/api/platform/roles?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
