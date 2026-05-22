"""Tests for GET /api/permissions/catalog.

The route is authenticated but ungated — every logged-in caller gets the
same payload because the catalog is non-secret data. Tests assert: 200 + every
CATALOG entry present + shape conformance + identical payload for
super_admin / generic-logged-in caller + 401 unauthenticated +
idempotence across calls.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser
from xtrusio_api.rbac.catalog import CATALOG

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def generic_logged_in_user() -> AsyncIterator[PlatformUser]:
    """A provisioned platform user with NO platform-role grants — used to
    confirm the catalog payload is identical for any authenticated caller,
    independent of permissions."""
    user_id = uuid4()
    email = f"pcat-generic-{user_id.hex[:8]}@example.com"
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


async def test_catalog_unauthenticated_401(http_client: AsyncClient) -> None:
    resp = await http_client.get("/api/permissions/catalog")
    assert resp.status_code == 401


async def test_catalog_returns_every_permission(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    resp = await http_client.get(
        "/api/permissions/catalog",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    keys_in_payload = {item["key"] for item in body["items"]}
    keys_in_catalog = {p.key for p in CATALOG}
    assert keys_in_payload == keys_in_catalog


async def test_catalog_shape_conforms(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    resp = await http_client.get(
        "/api/permissions/catalog",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.json()
    for item in body["items"]:
        assert set(item.keys()) == {"scope", "key", "category", "description"}
        assert item["scope"] in {"platform", "workspace"}
        assert isinstance(item["key"], str) and item["key"]
        assert isinstance(item["category"], str) and item["category"]
        assert isinstance(item["description"], str) and item["description"]


async def test_catalog_identical_for_generic_and_super_admin(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    generic_logged_in_user: PlatformUser,
) -> None:
    sa_token = make_jwt(sub=existing_super_admin.id)
    gen_token = make_jwt(sub=generic_logged_in_user.id)
    s = (
        await http_client.get(
            "/api/permissions/catalog",
            headers={"Authorization": f"Bearer {sa_token}"},
        )
    ).json()
    e = (
        await http_client.get(
            "/api/permissions/catalog",
            headers={"Authorization": f"Bearer {gen_token}"},
        )
    ).json()
    assert s == e


async def test_catalog_idempotent(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    first = await http_client.get(
        "/api/permissions/catalog",
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await http_client.get(
        "/api/permissions/catalog",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.json() == second.json()
