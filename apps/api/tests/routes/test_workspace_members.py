"""Tests for ``GET /api/workspaces/{workspace_id}/members``."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _provision_owner_workspace(member_role: str = "editor") -> tuple[UUID, UUID, UUID]:
    """Seed (workspace, owner_id, member_id) where owner holds
    workspace.members.read and member holds whatever the role implies.
    """
    owner_id, tid, member_id = uuid4(), uuid4(), uuid4()
    o_email = f"p6da-wmr-owner-{owner_id.hex[:8]}@example.com"
    m_email = f"p6da-wmr-mem-{member_id.hex[:8]}@example.com"
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
            {"t": str(tid), "s": f"p6da-wmr-{tid.hex[:8]}", "n": "wm-rt", "u": str(owner_id)},
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


async def _seed_non_member(label: str) -> UUID:
    uid = uuid4()
    email = f"{label}-{uid.hex[:8]}@example.com"
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
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(uid), "e": email},
        )
        await s.commit()
    return uid


async def test_list_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get(f"/api/workspaces/{uuid4()}/members")
    assert res.status_code == 401


async def test_list_403_for_non_member(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """A user with no membership in this workspace must 403 (no perm)."""
    tid, _, _ = await _provision_owner_workspace()
    outsider = await _seed_non_member("p6da-wmr-outsider")
    token = make_jwt(sub=outsider)
    res = await http_client.get(
        f"/api/workspaces/{tid}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_list_200_for_workspace_owner(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Owner sees both members (themselves + the editor)."""
    tid, owner_id, member_id = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/members?limit=200",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["items"], list)
    ids = {i["user_id"] for i in body["items"]}
    assert ids == {str(owner_id), str(member_id)}
    by_uid = {i["user_id"]: i for i in body["items"]}
    assert by_uid[str(owner_id)]["role"] == "owner"
    assert by_uid[str(member_id)]["role"] == "editor"
    assert by_uid[str(owner_id)]["email"].endswith("@example.com")
    assert "next_cursor" in body


async def test_list_invalid_cursor_400(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/members?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid cursor"


async def test_list_grant_count_per_member(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Owner row's granted_role_count reflects the reconciled owner grant."""
    tid, owner_id, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/members?limit=200",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    owner_row = next(i for i in res.json()["items"] if i["user_id"] == str(owner_id))
    # reconcile_user_roles_from_enums seeded the owner's user_roles row.
    assert owner_row["granted_role_count"] >= 1


async def test_list_403_for_other_workspaces_owner(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Owner of workspace A cannot list members of workspace B."""
    _, owner_a, _ = await _provision_owner_workspace()
    tid_b, _, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_a)
    res = await http_client.get(
        f"/api/workspaces/{tid_b}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"
