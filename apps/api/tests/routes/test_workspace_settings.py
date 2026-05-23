"""Tests for ``GET/PUT /api/workspaces/{wid}/settings``."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _provision_owner_workspace(member_role: str = "editor") -> tuple[UUID, UUID, UUID]:
    """Seed a workspace + owner + editor. Returns (tid, owner_id, editor_id)."""
    owner_id, tid, member_id = uuid4(), uuid4(), uuid4()
    o_email = f"p6da-wsr-owner-{owner_id.hex[:8]}@example.com"
    m_email = f"p6da-wsr-mem-{member_id.hex[:8]}@example.com"
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
            {"t": str(tid), "s": f"p6da-wsr-{tid.hex[:8]}", "n": "before", "u": str(owner_id)},
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


async def test_get_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get(f"/api/workspaces/{uuid4()}/settings")
    assert res.status_code == 401


async def test_put_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.put(f"/api/workspaces/{uuid4()}/settings", json={"name": "x"})
    assert res.status_code == 401


async def test_get_403_for_non_member(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, _, _ = await _provision_owner_workspace()
    outsider = await _seed_non_member("p6da-wsr-out")
    token = make_jwt(sub=outsider)
    res = await http_client.get(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_get_200_for_owner(http_client: AsyncClient, make_jwt: Callable[..., str]) -> None:
    tid, owner_id, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == str(tid)
    assert body["name"] == "before"
    assert body["slug"].startswith("p6da-wsr-")
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


async def test_get_200_for_editor_with_settings_read(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Editor role has workspace.settings.read (from SYSTEM_ROLE_PERMISSIONS)."""
    tid, _, editor_id = await _provision_owner_workspace(member_role="editor")
    token = make_jwt(sub=editor_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text


async def test_put_200_renames(http_client: AsyncClient, make_jwt: Callable[..., str]) -> None:
    tid, owner_id, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.put(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "after"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "after"
    # Subsequent GET also reflects the rename.
    get_res = await http_client.get(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.json()["name"] == "after"


async def test_put_403_for_editor(http_client: AsyncClient, make_jwt: Callable[..., str]) -> None:
    """Editor lacks workspace.settings.manage → 403."""
    tid, _, editor_id = await _provision_owner_workspace(member_role="editor")
    token = make_jwt(sub=editor_id)
    res = await http_client.put(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "should-not-apply"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_put_422_on_empty_name(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.put(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": ""},
    )
    assert res.status_code == 422


async def test_put_422_on_oversized_name(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    oversize = "a" * 201
    res = await http_client.put(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": oversize},
    )
    assert res.status_code == 422


async def test_get_403_for_other_workspaces_owner(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Owner of workspace A cannot read workspace B's settings."""
    _, owner_a, _ = await _provision_owner_workspace()
    tid_b, _, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_a)
    res = await http_client.get(
        f"/api/workspaces/{tid_b}/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_put_noop_does_not_write_audit(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Rename to the same value writes no audit row."""
    tid, owner_id, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.put(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "before"},
    )
    assert res.status_code == 200, res.text
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT count(*) FROM rbac_audit_log "
                    "WHERE workspace_id = :w AND action = 'workspace.settings.updated'"
                ),
                {"w": str(tid)},
            )
        ).scalar_one()
        assert int(rows) == 0


async def test_put_writes_audit_with_diff(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Successful rename writes a workspace.settings.updated row with diff."""
    tid, owner_id, _ = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.put(
        f"/api/workspaces/{tid}/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "rebrand"},
    )
    assert res.status_code == 200, res.text
    async with SessionLocal() as s:
        row = (
            await s.execute(
                text(
                    "SELECT before, after, actor_auth_user_id "
                    "FROM rbac_audit_log "
                    "WHERE workspace_id = :w AND action = 'workspace.settings.updated'"
                ),
                {"w": str(tid)},
            )
        ).one()
        before, after, actor = row
        assert before == {"name": "before"}
        assert after == {"name": "rebrand"}
        assert UUID(str(actor)) == owner_id
