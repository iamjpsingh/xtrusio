"""Tests for /api/tenants list + create."""

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
async def editor_user() -> AsyncIterator[PlatformUser]:
    user_id = uuid4()
    email = f"editor-{user_id.hex[:8]}@example.com"
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
            await s.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
            await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await s.commit()


async def test_list_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/tenants")
    assert res.status_code == 401


async def test_list_403_for_non_super_admin(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    editor_user: PlatformUser,
) -> None:
    token = make_jwt(sub=editor_user.id)
    res = await http_client.get("/api/tenants", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


async def test_list_empty_for_super_admin(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    super_admin_user: PlatformUser,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    res = await http_client.get("/api/tenants", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == []


async def test_create_tenant_succeeds(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    super_admin_user: PlatformUser,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    res = await http_client.post(
        "/api/tenants",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "acme-corp", "name": "Acme Corp"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["slug"] == "acme-corp"
    assert body["name"] == "Acme Corp"
    assert "id" in body

    # Cleanup
    async with SessionLocal() as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": body["id"]})
        await s.commit()


async def test_create_tenant_slug_conflict(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    super_admin_user: PlatformUser,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    headers = {"Authorization": f"Bearer {token}"}
    a = await http_client.post(
        "/api/tenants", headers=headers, json={"slug": "globex", "name": "Globex"}
    )
    assert a.status_code == 201
    b = await http_client.post(
        "/api/tenants", headers=headers, json={"slug": "globex", "name": "Globex 2"}
    )
    assert b.status_code == 409

    async with SessionLocal() as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": a.json()["id"]})
        await s.commit()


async def test_create_tenant_invalid_slug(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    super_admin_user: PlatformUser,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    res = await http_client.post(
        "/api/tenants",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "Bad Slug!", "name": "X"},
    )
    assert res.status_code == 422
