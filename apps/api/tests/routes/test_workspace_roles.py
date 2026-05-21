"""Tests for /api/workspaces/{wid}/roles CRUD."""

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


@pytest_asyncio.fixture
async def owner_workspace() -> AsyncIterator[tuple[UUID, UUID]]:
    """Fresh @example.com owner + tenant + system workspace roles wired.
    Yields (workspace_id, owner_user_id)."""
    uid, tid = uuid4(), uuid4()
    email = f"wsr-rt-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
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
        # Owners must also be platform users so the JWT->CurrentUser path
        # resolves. Use the lowest-priv enum value (`editor`); the workspace
        # 'owner' grant comes from tenant_memberships projection below.
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"wsr-rt-{tid.hex[:8]}", "n": "rt", "u": str(uid)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await s.commit()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    try:
        yield tid, uid
    finally:
        # _cleanup.py sweeps everything tied to this @example.com user via
        # tenants.created_by, so explicit teardown is belt-and-suspenders.
        pass


@pytest_asyncio.fixture
async def member_no_role_manage() -> AsyncIterator[PlatformUser]:
    """A platform user with NO workspace grants — used for 403 tests."""
    uid = uuid4()
    email = f"wsr-rt-noperm-{uid.hex[:8]}@example.com"
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
        pu = PlatformUser(id=uid, email=email, role=PlatformRole.EDITOR, is_active=True)
        s.add(pu)
        await s.commit()
        await s.refresh(pu)
    yield pu


async def test_list_requires_auth(
    http_client: AsyncClient, owner_workspace: tuple[UUID, UUID]
) -> None:
    tid, _ = owner_workspace
    res = await http_client.get(f"/api/workspaces/{tid}/roles")
    assert res.status_code == 401


async def test_list_403_for_non_member(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
    member_no_role_manage: PlatformUser,
) -> None:
    tid, _ = owner_workspace
    token = make_jwt(sub=member_no_role_manage.id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/roles", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_list_200_for_owner(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.get(
        f"/api/workspaces/{tid}/roles", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    keys = {r["key"] for r in body["items"]}
    # All four workspace system roles present.
    assert {"owner", "admin", "editor", "read_only"}.issubset(keys)


async def test_create_role_201_happy(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key": "auditor_ws",
            "name": "WS Auditor",
            "description": "viewers",
            "permission_keys": ["workspace.audit.read"],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["key"] == "auditor_ws"
    assert body["is_system"] is False
    assert body["workspace_id"] == str(tid)
    assert body["permission_keys"] == ["workspace.audit.read"]


async def test_create_role_409_duplicate_key(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    headers = {"Authorization": f"Bearer {token}"}
    a = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers=headers,
        json={"key": "dup_ws", "name": "Dup", "permission_keys": []},
    )
    assert a.status_code == 201, a.text
    b = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers=headers,
        json={"key": "dup_ws", "name": "Dup 2", "permission_keys": []},
    )
    assert b.status_code == 409
    assert b.json()["detail"] == "role_key_taken"


async def test_create_role_422_unknown_perm(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"key": "bogus_ws", "name": "Bogus", "permission_keys": ["bogus.x.y"]},
    )
    assert res.status_code == 422


async def test_create_role_422_scope_mismatch(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key": "scope_ws",
            "name": "Bad scope",
            "permission_keys": ["platform.users.read"],
        },
    )
    assert res.status_code == 422


async def test_get_role_404_unknown(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.get(
        f"/api/workspaces/{tid}/roles/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "role_not_found"


async def test_patch_system_role_422(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    headers = {"Authorization": f"Bearer {token}"}
    lst = await http_client.get(f"/api/workspaces/{tid}/roles", headers=headers)
    owner = next(r for r in lst.json()["items"] if r["key"] == "owner")
    res = await http_client.patch(
        f"/api/workspaces/{tid}/roles/{owner['id']}",
        headers=headers,
        json={"name": "renamed-owner"},
    )
    assert res.status_code == 422
    assert res.json()["detail"] == "system_role_immutable"


async def test_delete_custom_role_204(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    headers = {"Authorization": f"Bearer {token}"}
    c = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers=headers,
        json={"key": "del_me_ws", "name": "Doomed", "permission_keys": []},
    )
    assert c.status_code == 201, c.text
    rid = c.json()["id"]
    d = await http_client.delete(f"/api/workspaces/{tid}/roles/{rid}", headers=headers)
    assert d.status_code == 204
    g = await http_client.get(f"/api/workspaces/{tid}/roles/{rid}", headers=headers)
    assert g.status_code == 404


async def test_list_rejects_invalid_cursor(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.get(
        f"/api/workspaces/{tid}/roles?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid cursor"
