"""Tests for GET /api/workspaces/{wid}/audit-log."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.audit import write_audit_event
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _provision_owner_workspace() -> tuple[UUID, UUID]:
    """Returns (workspace_id, owner_user_id). Owner holds workspace.audit.read."""
    owner_id, tid = uuid4(), uuid4()
    email = f"waudit-rt-{owner_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(owner_id), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(owner_id), "e": email},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"waudit-rt-{tid.hex[:8]}", "n": "wa-rt", "u": str(owner_id)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(owner_id)},
        )
        await s.commit()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return tid, owner_id


async def _seed_event(actor_id: UUID, workspace_id: UUID, action: str) -> None:
    async with SessionLocal() as s:
        await write_audit_event(
            s,
            actor_id=actor_id,
            action=action,
            target_type="role",
            target_id=uuid4(),
            scope="workspace",
            workspace_id=workspace_id,
        )
        await s.commit()


async def test_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get(f"/api/workspaces/{uuid4()}/audit-log")
    assert res.status_code == 401


async def test_403_for_non_member(http_client: AsyncClient, make_jwt: Callable[..., str]) -> None:
    tid, _ = await _provision_owner_workspace()
    non_member = uuid4()
    email = f"waudit-rt-nm-{non_member.hex[:8]}@example.com"
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
        f"/api/workspaces/{tid}/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_200_for_owner_shape(http_client: AsyncClient, make_jwt: Callable[..., str]) -> None:
    tid, owner_id = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["items"], list)
    assert "next_cursor" in body
    for r in body["items"]:
        assert r["scope"] == "workspace"
        assert r["workspace_id"] == str(tid)


async def test_paginates_with_cursor(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id = await _provision_owner_workspace()
    for i in range(3):
        await _seed_event(owner_id, tid, f"test_p5d2_route.{i}")
    token = make_jwt(sub=owner_id)
    headers = {"Authorization": f"Bearer {token}"}
    collected: list[dict[str, object]] = []
    cursor: str | None = None
    safety = 0
    while safety < 100:
        url = f"/api/workspaces/{tid}/audit-log?limit=2"
        if cursor is not None:
            url += f"&cursor={cursor}"
        r = await http_client.get(url, headers=headers)
        assert r.status_code == 200, r.text
        page = r.json()
        collected.extend(
            row for row in page["items"] if str(row["action"]).startswith("test_p5d2_route.")
        )
        cursor = page["next_cursor"]
        if cursor is None or len(collected) >= 3:
            break
        safety += 1
    assert {row["action"] for row in collected} == {
        "test_p5d2_route.0",
        "test_p5d2_route.1",
        "test_p5d2_route.2",
    }


async def test_invalid_cursor_400(http_client: AsyncClient, make_jwt: Callable[..., str]) -> None:
    tid, owner_id = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/audit-log?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid cursor"
