"""Tests for ``POST /api/platform/users`` (super_admin direct-create).

Auth gate: ``super_admin`` role ONLY (provisioning platform staff is
non-delegatable). Both an unprivileged editor AND a platform ``admin`` must
403. Supabase is mocked via the shared ``mock_supabase_admin`` fixture so no
real auth user is created; the @example.com convention drives crash-proof
teardown. No test creates a real super_admin — the privileged actor is the
read-only ``existing_super_admin``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from gotrue.errors import AuthApiError
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _cleanup_email(email: str) -> None:
    """Crash-proof teardown for a created @example.com platform user."""
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        rows = (
            await s.execute(text("SELECT id FROM platform_users WHERE email = :e"), {"e": email})
        ).all()
        for (uid,) in rows:
            await s.execute(
                text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :u"),
                {"u": str(uid)},
            )
            await s.execute(
                text("DELETE FROM user_roles WHERE auth_user_id = :u OR granted_by = :u"),
                {"u": str(uid)},
            )
        await s.execute(text("DELETE FROM platform_users WHERE email = :e"), {"e": email})
        await s.execute(text("DELETE FROM auth.users WHERE email = :e"), {"e": email})
        await s.commit()


@pytest_asyncio.fixture
async def unprivileged_user() -> AsyncIterator[PlatformUser]:
    """Platform editor with no platform-role grants → no platform perms."""
    uid = uuid4()
    email = f"puc-noperm-{uid.hex[:8]}@example.com"
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
        await _cleanup_email(email)


@pytest_asyncio.fixture
async def platform_admin_user() -> AsyncIterator[PlatformUser]:
    """A platform ``admin`` (holds platform.users.manage) — must STILL 403:
    provisioning is super_admin-only, not delegatable to admins."""
    uid = uuid4()
    email = f"puc-admin-{uid.hex[:8]}@example.com"
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
        pu = PlatformUser(id=uid, email=email, role=PlatformRole.ADMIN, is_active=True)
        s.add(pu)
        await s.commit()
        await s.refresh(pu)
    try:
        yield pu
    finally:
        await _cleanup_email(email)


def _stub_created_user(mock_supabase_admin: MagicMock, user_id: str) -> None:
    mock_supabase_admin.auth.admin.create_user.return_value = MagicMock(user=MagicMock(id=user_id))


async def _seed_auth_user(user_id: str, email: str) -> None:
    """Mirror what the real Supabase Admin ``create_user`` would persist in
    ``auth.users`` — required because the mocked client doesn't actually write
    the row that ``user_roles.auth_user_id`` FK-references."""
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": user_id, "e": email},
        )
        await s.commit()


async def test_create_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.post(
        "/api/platform/users",
        json={"email": "x@example.com", "password": "Password1!", "role": "admin"},
    )
    assert res.status_code == 401


async def test_create_403_for_unprivileged(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
    mock_supabase_admin: MagicMock,
) -> None:
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.post(
        "/api/platform/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "denied@example.com", "password": "Password1!", "role": "admin"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"
    # The gate runs BEFORE any Supabase call.
    mock_supabase_admin.auth.admin.create_user.assert_not_called()


async def test_create_403_for_platform_admin(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    platform_admin_user: PlatformUser,
    mock_supabase_admin: MagicMock,
) -> None:
    """A platform admin holds platform.users.manage but is NOT super_admin →
    403. Provisioning platform staff is super_admin-only."""
    token = make_jwt(sub=platform_admin_user.id)
    res = await http_client.post(
        "/api/platform/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "admin-created@example.com", "password": "Password1!", "role": "admin"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"
    mock_supabase_admin.auth.admin.create_user.assert_not_called()


async def test_create_super_admin_pinned_role_rejected_422(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    mock_supabase_admin: MagicMock,
) -> None:
    """``super_admin`` is not an accepted role value (schema Literal['admin'])."""
    token = make_jwt(sub=existing_super_admin.id)
    res = await http_client.post(
        "/api/platform/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "promote@example.com", "password": "Password1!", "role": "super_admin"},
    )
    assert res.status_code == 422
    mock_supabase_admin.auth.admin.create_user.assert_not_called()


async def test_create_happy_path_201(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    mock_supabase_admin: MagicMock,
) -> None:
    email = f"puc-new-{uuid4().hex[:8]}@example.com"
    new_id = str(uuid4())
    _stub_created_user(mock_supabase_admin, new_id)
    # The mocked Admin API doesn't persist auth.users; seed the row the real
    # call would create so the user_roles FK is satisfiable.
    await _seed_auth_user(new_id, email)
    token = make_jwt(sub=existing_super_admin.id)
    try:
        res = await http_client.post(
            "/api/platform/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": email, "password": "Password1!", "role": "admin"},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["id"] == new_id
        assert body["email"] == email
        assert body["role"] == "admin"
        assert body["is_active"] is True
        # email_confirm: True (operator provisioning, no confirmation round-trip).
        mock_supabase_admin.auth.admin.create_user.assert_called_once()
        call_arg = mock_supabase_admin.auth.admin.create_user.call_args.args[0]
        assert call_arg["email_confirm"] is True
        # The platform_users row + the platform 'admin' grant must both exist.
        async with SessionLocal() as s:
            pu = (
                await s.execute(
                    text("SELECT role, is_active FROM platform_users WHERE id = :i"),
                    {"i": new_id},
                )
            ).first()
            assert pu is not None and pu[0] == "admin" and pu[1] is True
            grant_count = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                        "WHERE ur.auth_user_id = :u AND r.scope = 'platform' AND r.key = 'admin'"
                    ),
                    {"u": new_id},
                )
            ).scalar_one()
            assert grant_count == 1
    finally:
        await _cleanup_email(email)


async def test_create_duplicate_email_409(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
    mock_supabase_admin: MagicMock,
) -> None:
    """A gotrue ``email_exists`` from the Admin API maps to 409, no DB write."""
    email = f"puc-dup-{uuid4().hex[:8]}@example.com"
    mock_supabase_admin.auth.admin.create_user.side_effect = AuthApiError(
        "email already registered", 422, "email_exists"
    )
    token = make_jwt(sub=existing_super_admin.id)
    try:
        res = await http_client.post(
            "/api/platform/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": email, "password": "Password1!", "role": "admin"},
        )
        assert res.status_code == 409, res.text
        assert res.json()["detail"] == "user_exists"
        async with SessionLocal() as s:
            present = (
                await s.execute(text("SELECT 1 FROM platform_users WHERE email = :e"), {"e": email})
            ).first()
            assert present is None
    finally:
        await _cleanup_email(email)
