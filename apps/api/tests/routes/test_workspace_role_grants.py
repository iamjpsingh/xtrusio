"""Tests for /api/workspaces/{wid}/members/{uid}/roles grant/revoke/list."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _provision_owner_and_member(
    member_role: str = "editor",
) -> tuple[UUID, UUID, UUID]:
    """Returns (workspace_id, owner_user_id, member_user_id). Both are
    @example.com users; tenant + tenant_memberships seeded; user_roles wired
    via the reconciler."""
    owner_id, tid, member_id = uuid4(), uuid4(), uuid4()
    o_email = f"wrg-rt-owner-{owner_id.hex[:8]}@example.com"
    m_email = f"wrg-rt-mem-{member_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        for uid, email in ((owner_id, o_email), (member_id, m_email)):
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
                    "INSERT INTO platform_users (id, email, role, is_active) "
                    "VALUES (:id, :e, 'editor', true)"
                ),
                {"id": str(uid), "e": email},
            )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"wrg-rt-{tid.hex[:8]}", "n": "rt", "u": str(owner_id)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :o, 'owner'), (:t, :m, :r)"
            ),
            {"t": str(tid), "o": str(owner_id), "m": str(member_id), "r": member_role},
        )
        await s.commit()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return tid, owner_id, member_id


async def _role_id(workspace_id: UUID, key: str) -> UUID:
    async with SessionLocal() as s:
        rid = (
            await s.execute(
                text(
                    "SELECT id FROM roles WHERE scope='workspace' "
                    "AND workspace_id = :w AND key = :k AND is_system"
                ),
                {"w": str(workspace_id), "k": key},
            )
        ).scalar_one()
        return UUID(str(rid))


async def test_get_list_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get(f"/api/workspaces/{uuid4()}/members/{uuid4()}/roles")
    assert res.status_code == 401


async def test_post_403_for_non_owner(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, _, member_id = await _provision_owner_and_member()
    # member_id is an editor — lacks workspace.members.manage.
    token = make_jwt(sub=member_id)
    admin_role = await _role_id(tid, "admin")
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(admin_role)},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_post_201_happy(http_client: AsyncClient, make_jwt: Callable[..., str]) -> None:
    tid, owner_id, member_id = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    admin_role = await _role_id(tid, "admin")
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(admin_role)},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["role_key"] == "admin"
    assert UUID(body["auth_user_id"]) == member_id
    assert UUID(body["workspace_id"]) == tid


async def test_post_404_non_member(http_client: AsyncClient, make_jwt: Callable[..., str]) -> None:
    tid, owner_id, _ = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    admin_role = await _role_id(tid, "admin")
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{uuid4()}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(admin_role)},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "membership_not_found"


async def test_post_404_role_not_found(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, member_id = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(uuid4())},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "role_not_found"


async def test_post_403_privilege_escalation(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """An admin (workspace_admin role; lacks workspace.roles.manage) tries to
    grant the workspace owner role. The route gate require_permission for
    workspace.members.manage passes (admin has it), but the service's
    priv-escalation pre-check sees the actor lacks workspace.roles.manage and
    returns 403."""
    tid, _, admin_actor = await _provision_owner_and_member(member_role="admin")
    token = make_jwt(sub=admin_actor)
    owner_role = await _role_id(tid, "owner")
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{admin_actor}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(owner_role)},
    )
    assert res.status_code == 403, res.text
    # PAR-A M22: sanitized body — no perm key leak.
    assert res.json()["detail"] == "privilege_escalation"


async def test_delete_204_happy(http_client: AsyncClient, make_jwt: Callable[..., str]) -> None:
    tid, owner_id, member_id = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    headers = {"Authorization": f"Bearer {token}"}
    admin_role = await _role_id(tid, "admin")
    post_res = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers=headers,
        json={"role_id": str(admin_role)},
    )
    assert post_res.status_code == 201, post_res.text
    grant_id = post_res.json()["id"]
    del_res = await http_client.delete(
        f"/api/workspaces/{tid}/members/{member_id}/roles/{grant_id}",
        headers=headers,
    )
    assert del_res.status_code == 204


async def test_delete_409_owner_floor(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Workspace has exactly one owner — deleting that owner grant must 409."""
    tid, owner_id, _ = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    # Find the owner's owner-role grant id.
    async with SessionLocal() as s:
        owner_grant_id = (
            await s.execute(
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
    res = await http_client.delete(
        f"/api/workspaces/{tid}/members/{owner_id}/roles/{owner_grant_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "owner_floor"


async def test_delete_404_cross_workspace_grant_id(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Pass a grant_id from workspace B to a DELETE under workspace A => 404.
    Scope isolation regression guard."""
    tid_a, owner_a, _ = await _provision_owner_and_member()
    tid_b, _, member_b = await _provision_owner_and_member()
    token = make_jwt(sub=owner_a)
    # member_b has an editor grant in tid_b — fetch its id.
    async with SessionLocal() as s:
        grant_b_id = (
            await s.execute(
                text(
                    "SELECT ur.id FROM user_roles ur "
                    "JOIN roles r ON r.id = ur.role_id "
                    "WHERE r.scope='workspace' AND r.workspace_id = :w "
                    "AND ur.auth_user_id = :u"
                ),
                {"w": str(tid_b), "u": str(member_b)},
            )
        ).scalar_one()
    res = await http_client.delete(
        f"/api/workspaces/{tid_a}/members/{member_b}/roles/{grant_b_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    # member_b isn't even a member of tid_a — but require_permission only
    # checks the ACTOR's perms in tid_a. The route gate passes (owner_a has
    # workspace.members.manage in tid_a), so the service-level check fires:
    # the grant lookup pinned to (id, user_id, workspace_id=tid_a) returns
    # None => 404 grant_not_found.
    assert res.status_code == 404
    assert res.json()["detail"] == "grant_not_found"


async def test_list_paginates_with_cursor(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, member_id = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    headers = {"Authorization": f"Bearer {token}"}
    # Grant 'admin' to member_id (already has editor); two grants total.
    admin_role = await _role_id(tid, "admin")
    r = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers=headers,
        json={"role_id": str(admin_role)},
    )
    assert r.status_code == 201, r.text
    r1 = await http_client.get(
        f"/api/workspaces/{tid}/members/{member_id}/roles?limit=1", headers=headers
    )
    assert r1.status_code == 200
    p1 = r1.json()
    assert len(p1["items"]) == 1
    assert p1["next_cursor"] is not None
    r2 = await http_client.get(
        f"/api/workspaces/{tid}/members/{member_id}/roles" f"?limit=1&cursor={p1['next_cursor']}",
        headers=headers,
    )
    assert r2.status_code == 200
    p2 = r2.json()
    assert len(p2["items"]) == 1
    assert p1["items"][0]["id"] != p2["items"][0]["id"]


async def test_get_403_for_lacking_members_read(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """GET is gated by workspace.members.read (held by owner, admin, editor,
    read_only — i.e., every workspace system role). Use a non-member to 403."""
    tid, _, _ = await _provision_owner_and_member()
    # Fresh non-member user.
    non_member = uuid4()
    email = f"wrg-rt-nm-{non_member.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(non_member), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(non_member), "e": email},
        )
        await s.commit()
    token = make_jwt(sub=non_member)
    res = await http_client.get(
        f"/api/workspaces/{tid}/members/{non_member}/roles",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
