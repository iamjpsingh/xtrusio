"""Tests for POST/GET/DELETE /api/platform/users/invites."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser
from xtrusio_api.services.platform_invites import create_platform_invite

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_create_invite_unauth_returns_401(http_client: AsyncClient) -> None:
    r = await http_client.post(
        "/api/platform/users/invites", json={"email": "a@a.com", "role": "admin"}
    )
    assert r.status_code == 401


async def _seed_platform_user(db: AsyncSession, *, role_key: str | None) -> UUID:
    """Ephemeral auth.users + platform_users row; if `role_key` is given, also a
    resolver-visible platform `user_roles` grant (the P3b authz source). No
    super_admin is ever created (use the `existing_super_admin` fixture)."""
    from xtrusio_api.models.platform_user import PlatformRole
    from xtrusio_api.models.platform_user import PlatformUser as PlatformUserModel
    from xtrusio_api.rbac.grants import grant_role

    user_id = uuid4()
    email = f"pu-{user_id.hex[:8]}@example.com"
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    db.add(PlatformUserModel(id=user_id, email=email, role=PlatformRole.EDITOR, is_active=True))
    if role_key is not None:
        await grant_role(db, auth_user_id=user_id, scope="platform", key=role_key)
    await db.commit()
    return user_id


async def _drop_platform_user(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(text("DELETE FROM user_roles WHERE auth_user_id = :id"), {"id": str(user_id)})
    await db.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
    await db.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
    await db.commit()


async def test_create_invite_unprivileged_returns_403_permission_denied(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt: Callable[..., str]
) -> None:
    # P3b authz model: a principal without `platform.users.invite` (no platform
    # role grant) is denied with the unified permission_denied contract.
    user_id = await _seed_platform_user(db_session, role_key=None)
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            "/api/platform/users/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@x.com", "role": "admin"},
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "permission_denied"
    finally:
        await _drop_platform_user(db_session, user_id)


async def test_create_invite_platform_admin_succeeds(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    # P3b intentionally CHANGES authz: platform `admin` now holds
    # `platform.users.invite` (spec matrix) and may create invites.
    user_id = await _seed_platform_user(db_session, role_key="admin")
    try:
        mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            "/api/platform/users/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "admin-invited@example.com", "role": "admin"},
        )
        assert r.status_code == 201
        assert r.json()["email"] == "admin-invited@example.com"
        await db_session.execute(
            text("DELETE FROM platform_invites WHERE email = :e"),
            {"e": "admin-invited@example.com"},
        )
        await db_session.commit()
    finally:
        await _drop_platform_user(db_session, user_id)


async def test_create_editor_platform_invite_rejected_400(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    """PAR-D L5: 'editor' has no platform RBAC system role (accepting it would
    create a roleless platform user), so the invite is rejected up front."""
    user_id = await _seed_platform_user(db_session, role_key="admin")
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            "/api/platform/users/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "editor-invited@example.com", "role": "editor"},
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "unsupported_invite_role"
    finally:
        await _drop_platform_user(db_session, user_id)


async def test_create_invite_happy_path(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    sb_uid = str(uuid4())
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock(
        user=MagicMock(id=sb_uid)
    )
    r = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "newadmin@example.com", "role": "admin"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "newadmin@example.com"
    assert body["role"] == "admin"
    # PAR-D H5: create no longer calls Supabase on the request path — it stages
    # an outbox row (the worker sends it out of band). Assert the row was
    # enqueued with the right app_metadata + writeback, and Supabase was untouched.
    mock_supabase_admin.auth.admin.invite_user_by_email.assert_not_called()
    payload = (
        await db_session.execute(
            text(
                "SELECT payload FROM invite_email_outbox "
                "WHERE payload->>'email' = :e ORDER BY created_at DESC LIMIT 1"
            ),
            {"e": "newadmin@example.com"},
        )
    ).scalar_one()
    assert payload["email"] == "newadmin@example.com"
    assert payload["app_metadata"]["platform_invite_id"] == body["id"]
    assert payload["app_metadata"]["platform_role"] == "admin"
    assert payload["writeback"] == {"table": "platform_invites", "id": body["id"]}
    await db_session.execute(
        text("DELETE FROM invite_email_outbox WHERE payload->>'email' = :e"),
        {"e": "newadmin@example.com"},
    )
    await db_session.execute(
        text("DELETE FROM platform_invites WHERE email = :e"), {"e": "newadmin@example.com"}
    )
    await db_session.commit()


async def test_create_invite_duplicate_pending_returns_409(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
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
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
    await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "listed@example.com", "role": "admin"},
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
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    sb_uid = str(uuid4())
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock(
        user=MagicMock(id=sb_uid)
    )
    r = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "rev@example.com", "role": "admin"},
    )
    invite_id = r.json()["id"]
    # PAR-D H5: the outbox worker (not run in tests) sets supabase_user_id after
    # sending. Simulate the post-send state so revoke performs the Supabase
    # auth-user cleanup (which keys off supabase_user_id).
    await db_session.execute(
        text("UPDATE platform_invites SET supabase_user_id = CAST(:sid AS uuid) WHERE id = :id"),
        {"sid": sb_uid, "id": invite_id},
    )
    await db_session.commit()
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
    mock_supabase_admin.auth.admin.delete_user.assert_called_once()
    (called_id,), _ = mock_supabase_admin.auth.admin.delete_user.call_args
    assert called_id == sb_uid
    await db_session.execute(text("DELETE FROM platform_invites WHERE id = :id"), {"id": invite_id})
    await db_session.commit()


async def test_create_invite_super_admin_role_rejected_422(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    r = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "x@example.com", "role": existing_super_admin.role.value},
    )
    assert r.status_code == 422


async def test_list_platform_invites_paginates(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock(
        user=MagicMock(id=str(uuid4()))
    )
    async with SessionLocal() as s:
        for i in range(3):
            await create_platform_invite(
                s,
                email=f"paginv-{i}-{uuid4().hex[:6]}@example.com",
                role=PlatformRole.ADMIN,
                invited_by=existing_super_admin.id,
            )
        await s.commit()  # PAR-D M1: service is now caller-owns-tx

    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await http_client.get("/api/platform/users/invites?limit=2", headers=headers)
    assert r1.status_code == 200, r1.text
    p1 = r1.json()
    assert len(p1["items"]) == 2
    assert p1["next_cursor"] is not None

    r2 = await http_client.get(
        f"/api/platform/users/invites?limit=2&cursor={p1['next_cursor']}",
        headers=headers,
    )
    assert r2.status_code == 200, r2.text
    p2 = r2.json()
    assert len(p2["items"]) >= 1
    assert {x["id"] for x in p1["items"]}.isdisjoint({x["id"] for x in p2["items"]})


async def test_list_platform_invites_rejects_bad_cursor(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    r = await http_client.get(
        "/api/platform/users/invites?cursor=NOPE",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
