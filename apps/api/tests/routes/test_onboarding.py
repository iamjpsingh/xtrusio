"""Tests for POST /api/onboarding/tenants."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_unprovisioned_user(db: AsyncSession) -> tuple[UUID, str]:
    user_id = uuid4()
    email = f"new-{user_id.hex[:8]}@example.com"
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    await db.commit()
    return user_id, email


async def _cleanup_user(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(
        text("DELETE FROM tenant_memberships WHERE user_id = :id"),
        {"id": str(user_id)},
    )
    await db.execute(
        text("DELETE FROM tenants WHERE created_by = :id"),
        {"id": str(user_id)},
    )
    await db.execute(
        text("DELETE FROM auth.users WHERE id = :id"),
        {"id": str(user_id)},
    )
    await db.commit()


async def test_onboarding_unauth_returns_401(http_client: AsyncClient) -> None:
    r = await http_client.post("/api/onboarding/tenants", json={"workspace_name": "Acme Corp"})
    assert r.status_code == 401


async def test_onboarding_happy_path(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt: Callable[..., str],
) -> None:
    user_id, _email = await _make_unprovisioned_user(db_session)
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json={"workspace_name": "Acme Corp"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["tenant"]["slug"] == "acme-corp"
        assert body["tenant"]["name"] == "Acme Corp"
        assert body["tenant"]["role"] == "owner"
    finally:
        await _cleanup_user(db_session, user_id)


async def test_onboarding_slug_collision_appends_suffix(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt: Callable[..., str],
) -> None:
    user_id_a, _ = await _make_unprovisioned_user(db_session)
    user_id_b, _ = await _make_unprovisioned_user(db_session)
    try:
        token_a = make_jwt(sub=user_id_a)
        await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"workspace_name": "Acme Corp"},
        )
        token_b = make_jwt(sub=user_id_b)
        r = await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"workspace_name": "Acme Corp"},
        )
        assert r.status_code == 201
        assert r.json()["tenant"]["slug"] == "acme-corp-2"
    finally:
        await _cleanup_user(db_session, user_id_a)
        await _cleanup_user(db_session, user_id_b)


async def test_onboarding_already_has_membership_returns_409(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt: Callable[..., str],
) -> None:
    user_id, _ = await _make_unprovisioned_user(db_session)
    try:
        token = make_jwt(sub=user_id)
        await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json={"workspace_name": "First Workspace"},
        )
        r = await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json={"workspace_name": "Second Workspace"},
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "already_has_membership"
    finally:
        await _cleanup_user(db_session, user_id)
