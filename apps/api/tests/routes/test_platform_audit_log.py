"""Tests for GET /api/platform/audit-log.

Auth gate: ``platform.audit.read`` (held by both seeded system roles —
super_admin and admin). The unprivileged-user fixture holds no grants and
must therefore 403.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.audit import write_audit_event
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def unprivileged_user() -> AsyncIterator[PlatformUser]:
    """A provisioned platform user with NO platform-role grants — holds no
    platform permission, so `platform.audit.read` resolves false."""
    user_id = uuid4()
    email = f"paudit-noperm-{user_id.hex[:8]}@example.com"
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


async def _seed_audit_actor(actor_id: UUID, label: str) -> None:
    """Insert a minimal @example.com auth.users row so FK resolves and the
    session-scoped cleanup purges this actor + its audit rows on teardown.
    """
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
                "'authenticated', :email, '', now(), now(), now())"
            ),
            {"id": str(actor_id), "email": f"paudit-{label}-{actor_id.hex[:8]}@example.com"},
        )
        await s.commit()


async def _seed_event(actor_id: UUID, action: str) -> None:
    async with SessionLocal() as s:
        await write_audit_event(
            s,
            actor_id=actor_id,
            action=action,
            target_type="role",
            target_id=uuid4(),
            scope="platform",
        )
        await s.commit()


# --- auth / authz gates ----------------------------------------------------


async def test_list_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/platform/audit-log")
    assert res.status_code == 401


async def test_list_403_for_unprivileged(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
) -> None:
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.get(
        "/api/platform/audit-log", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_list_200_for_super_admin_shape(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.get(
        "/api/platform/audit-log", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["items"], list)
    assert "next_cursor" in body
    # Every returned row must be platform-scope (the endpoint's contract).
    for r in body["items"]:
        assert r["scope"] == "platform"


# --- pagination -----------------------------------------------------------


async def test_list_paginates(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    actor = uuid4()
    await _seed_audit_actor(actor, "page")
    for i in range(3):
        await _seed_event(actor, f"test_p4d1_route_page.{i}")

    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Walk pages with limit=2, collecting only this test's rows (filter by
    # action prefix to ignore noise from other tests).
    collected: list[dict[str, object]] = []
    cursor: str | None = None
    safety = 0
    while safety < 100:
        url = "/api/platform/audit-log?limit=2"
        if cursor is not None:
            url += f"&cursor={cursor}"
        r = await http_client.get(url, headers=headers)
        assert r.status_code == 200, r.text
        page = r.json()
        assert len(page["items"]) <= 2
        collected.extend(
            row for row in page["items"] if str(row["action"]).startswith("test_p4d1_route_page.")
        )
        cursor = page["next_cursor"]
        if cursor is None or len(collected) >= 3:
            break
        safety += 1

    assert len(collected) == 3
    assert {row["action"] for row in collected} == {
        "test_p4d1_route_page.0",
        "test_p4d1_route_page.1",
        "test_p4d1_route_page.2",
    }


async def test_list_rejects_invalid_cursor(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.get(
        "/api/platform/audit-log?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid cursor"
