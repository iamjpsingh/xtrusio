"""Tests for ``GET /api/platform/users``.

Auth gate: ``platform.users.read`` (held by both seeded platform system
roles). The unprivileged-user fixture has no grants and must therefore 403.
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


async def _seed_example_user(label: str = "p6da-pur") -> UUID:
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


async def _cleanup_user(uid: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :u"),
            {"u": str(uid)},
        )
        await s.execute(
            text("DELETE FROM user_roles WHERE auth_user_id = :u OR granted_by = :u"),
            {"u": str(uid)},
        )
        await s.execute(text("DELETE FROM platform_users WHERE id = :u"), {"u": str(uid)})
        await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(uid)})
        await s.commit()


@pytest_asyncio.fixture
async def unprivileged_user() -> AsyncIterator[PlatformUser]:
    """Platform editor with no platform-role grants → no platform perms."""
    uid = uuid4()
    email = f"p6da-pur-noperm-{uid.hex[:8]}@example.com"
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
    try:
        yield pu
    finally:
        await _cleanup_user(uid)


async def test_list_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/platform/users")
    assert res.status_code == 401


async def test_list_403_for_unprivileged(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
) -> None:
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.get("/api/platform/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_list_200_for_super_admin_shape(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    """Listing as super_admin returns the page shape with at least the
    super_admin row itself."""
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.get(
        "/api/platform/users?limit=200", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["items"], list)
    assert "next_cursor" in body
    super_admin_in_listing = [i for i in body["items"] if i["id"] == str(existing_super_admin.id)]
    assert super_admin_in_listing, "super_admin row missing from listing"
    row = super_admin_in_listing[0]
    assert row["email"] == existing_super_admin.email
    assert row["role"] == "super_admin"
    # super_admin holds the platform super_admin grant → count >= 1.
    assert row["granted_role_count"] >= 1


async def test_list_invalid_cursor_400(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.get(
        "/api/platform/users?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid cursor"


async def test_list_includes_seeded_user(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    """A freshly-seeded @example.com platform user must appear in the listing."""
    uid = await _seed_example_user("p6da-pur-seed")
    try:
        token = make_jwt(sub=existing_super_admin.id)
        res = await http_client.get(
            "/api/platform/users?limit=200",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200, res.text
        ids = {i["id"] for i in res.json()["items"]}
        assert str(uid) in ids
    finally:
        await _cleanup_user(uid)


async def test_list_paginates_with_cursor(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    """Walk the listing with limit=1, collecting our seeded ids until done."""
    seeded = [await _seed_example_user(f"p6da-pur-page-{i}") for i in range(3)]
    seeded_set = {str(s) for s in seeded}
    try:
        token = make_jwt(sub=existing_super_admin.id)
        headers = {"Authorization": f"Bearer {token}"}
        seen: set[str] = set()
        cursor: str | None = None
        safety = 0
        while safety < 500:
            url = "/api/platform/users?limit=1"
            if cursor is not None:
                url += f"&cursor={cursor}"
            r = await http_client.get(url, headers=headers)
            assert r.status_code == 200, r.text
            page = r.json()
            assert len(page["items"]) <= 1
            for item in page["items"]:
                if item["id"] in seeded_set:
                    seen.add(item["id"])
            cursor = page["next_cursor"]
            if cursor is None or seen == seeded_set:
                break
            safety += 1
        assert seen == seeded_set
    finally:
        for u in seeded:
            await _cleanup_user(u)
