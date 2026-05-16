"""Tests for POST/GET/DELETE /api/platform/users/invites."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_create_invite_unauth_returns_401(http_client: AsyncClient) -> None:
    r = await http_client.post(
        "/api/platform/users/invites", json={"email": "a@a.com", "role": "admin"}
    )
    assert r.status_code == 401


async def test_create_invite_non_super_admin_returns_403(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    from xtrusio_api.models.platform_user import PlatformRole
    from xtrusio_api.models.platform_user import PlatformUser as PlatformUserModel

    user_id = uuid4()
    email = f"editor-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    db_session.add(
        PlatformUserModel(id=user_id, email=email, role=PlatformRole.EDITOR, is_active=True)
    )
    await db_session.commit()
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            "/api/platform/users/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@x.com", "role": "admin"},
        )
        assert r.status_code == 403
    finally:
        await db_session.execute(
            text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)}
        )
        await db_session.execute(
            text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)}
        )
        await db_session.commit()


async def test_create_invite_happy_path(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
    r = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "newadmin@example.com", "role": "admin"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "newadmin@example.com"
    assert body["role"] == "admin"
    mock_supabase_admin.auth.admin.invite_user_by_email.assert_called_once()
    args, kwargs = mock_supabase_admin.auth.admin.invite_user_by_email.call_args
    assert args[0] == "newadmin@example.com"
    assert kwargs["data"]["platform_invite_id"] == body["id"]
    assert kwargs["data"]["platform_role"] == "admin"
    await db_session.execute(
        text("DELETE FROM platform_invites WHERE email = :e"), {"e": "newadmin@example.com"}
    )
    await db_session.commit()


async def test_create_invite_duplicate_pending_returns_409(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
    body = {"email": "dup@example.com", "role": "admin"}
    r1 = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert r1.status_code == 201
    r2 = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert r2.status_code == 409
    assert r2.json()["detail"] == "invite_pending"
    await db_session.execute(
        text("DELETE FROM platform_invites WHERE email = :e"), {"e": "dup@example.com"}
    )
    await db_session.commit()


async def test_list_invites_returns_created(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
    await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "listed@example.com", "role": "editor"},
    )
    r = await http_client.get(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert any(i["email"] == "listed@example.com" for i in body["items"])
    assert body["next_cursor"] is None
    await db_session.execute(
        text("DELETE FROM platform_invites WHERE email = :e"), {"e": "listed@example.com"}
    )
    await db_session.commit()


async def test_revoke_invite(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock(
        user=MagicMock(id=str(uuid4()))
    )
    r = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "rev@example.com", "role": "editor"},
    )
    invite_id = r.json()["id"]
    r = await http_client.delete(
        f"/api/platform/users/invites/{invite_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204
    row = (
        await db_session.execute(
            text("SELECT revoked_at FROM platform_invites WHERE id = :id"), {"id": invite_id}
        )
    ).scalar_one()
    assert row is not None
    await db_session.execute(text("DELETE FROM platform_invites WHERE id = :id"), {"id": invite_id})
    await db_session.commit()


async def test_create_invite_super_admin_role_rejected_422(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    r = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "x@example.com", "role": "super_admin"},
    )
    assert r.status_code == 422
