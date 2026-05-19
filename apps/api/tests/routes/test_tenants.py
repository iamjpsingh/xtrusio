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
from xtrusio_api.rbac.grants import grant_role

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def unprivileged_user() -> AsyncIterator[PlatformUser]:
    """A provisioned platform user with NO platform role grant — under the P3b
    permission model it holds no platform permission (the old enum `editor`
    case, reframed)."""
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
            await s.execute(
                text("DELETE FROM user_roles WHERE auth_user_id = :id"), {"id": str(user_id)}
            )
            await s.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
            await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await s.commit()


@pytest_asyncio.fixture
async def platform_admin_user() -> AsyncIterator[PlatformUser]:
    """A provisioned platform user with a resolver-visible `admin` platform
    grant. Under the P3b matrix `admin` holds platform.clients.read/manage."""
    user_id = uuid4()
    email = f"padm-{user_id.hex[:8]}@example.com"
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
        pu = PlatformUser(id=user_id, email=email, role=PlatformRole.ADMIN, is_active=True)
        s.add(pu)
        await grant_role(s, auth_user_id=user_id, scope="platform", key="admin")
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


async def test_list_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/tenants")
    assert res.status_code == 401


async def test_list_403_permission_denied_for_unprivileged(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
) -> None:
    # P3b: no `platform.clients.read` grant -> unified permission_denied.
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.get("/api/tenants", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_list_403_permission_denied_create_for_unprivileged(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
) -> None:
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.post(
        "/api/tenants",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "denied-co", "name": "Denied"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_list_and_create_succeed_for_platform_admin(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    platform_admin_user: PlatformUser,
) -> None:
    # P3b intentionally CHANGES authz: platform `admin` now holds
    # platform.clients.read/manage (spec matrix), not super_admin-only.
    token = make_jwt(sub=platform_admin_user.id)
    headers = {"Authorization": f"Bearer {token}"}
    lst = await http_client.get("/api/tenants", headers=headers)
    assert lst.status_code == 200
    crt = await http_client.post(
        "/api/tenants", headers=headers, json={"slug": "admin-made-co", "name": "Admin Co"}
    )
    assert crt.status_code == 201
    async with SessionLocal() as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": crt.json()["id"]})
        await s.commit()


async def test_list_empty_for_super_admin(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.get("/api/tenants", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == []


async def test_create_tenant_succeeds(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
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
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
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
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.post(
        "/api/tenants",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "Bad Slug!", "name": "X"},
    )
    assert res.status_code == 422
