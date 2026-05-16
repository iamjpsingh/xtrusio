"""Tests for POST /api/invites/accept."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _insert_auth_user(db: AsyncSession, user_id, email: str) -> None:
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )


async def test_no_invite_in_metadata_returns_403(
    http_client: AsyncClient, make_jwt, db_session: AsyncSession
) -> None:
    user_id = uuid4()
    await _insert_auth_user(db_session, user_id, f"x-{user_id.hex[:8]}@example.com")
    await db_session.commit()
    try:
        token = make_jwt(sub=user_id, user_metadata={})
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "no_invite"
    finally:
        await db_session.execute(
            text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)}
        )
        await db_session.commit()


async def test_accept_platform_invite_happy_path(
    http_client: AsyncClient, existing_super_admin, make_jwt, db_session: AsyncSession
) -> None:
    invite_id = uuid4()
    user_id = uuid4()
    email = f"new-platform-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO platform_invites "
            "(id, email, role, invited_by, expires_at, accepted_at, revoked_at) "
            "VALUES (:id, :email, 'admin', :inv, :exp, NULL, NULL)"
        ),
        {
            "id": str(invite_id),
            "email": email,
            "inv": str(existing_super_admin.id),
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
    )
    await _insert_auth_user(db_session, user_id, email)
    await db_session.commit()
    try:
        token = make_jwt(
            sub=user_id,
            user_metadata={"platform_invite_id": str(invite_id), "platform_role": "admin"},
        )
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "platform"
        assert body["role"] == "admin"
        row = (
            await db_session.execute(
                text("SELECT role FROM platform_users WHERE id = :id"), {"id": str(user_id)}
            )
        ).scalar_one()
        assert row == "admin"
        acc = (
            await db_session.execute(
                text("SELECT accepted_at FROM platform_invites WHERE id = :id"),
                {"id": str(invite_id)},
            )
        ).scalar_one()
        assert acc is not None
    finally:
        for stmt in (
            "DELETE FROM platform_users WHERE id = :id",
            "DELETE FROM platform_invites WHERE id = :iid",
            "DELETE FROM auth.users WHERE id = :id",
        ):
            await db_session.execute(text(stmt), {"id": str(user_id), "iid": str(invite_id)})
        await db_session.commit()


async def test_expired_invite_returns_403(
    http_client: AsyncClient, existing_super_admin, make_jwt, db_session: AsyncSession
) -> None:
    invite_id = uuid4()
    user_id = uuid4()
    email = f"exp-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO platform_invites (id, email, role, invited_by, expires_at) "
            "VALUES (:id, :email, 'editor', :inv, :exp)"
        ),
        {
            "id": str(invite_id),
            "email": email,
            "inv": str(existing_super_admin.id),
            "exp": datetime.now(UTC) - timedelta(days=1),
        },
    )
    await _insert_auth_user(db_session, user_id, email)
    await db_session.commit()
    try:
        token = make_jwt(
            sub=user_id,
            user_metadata={"platform_invite_id": str(invite_id), "platform_role": "editor"},
        )
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "invite_expired"
    finally:
        for stmt in (
            "DELETE FROM platform_invites WHERE id = :iid",
            "DELETE FROM auth.users WHERE id = :id",
        ):
            await db_session.execute(text(stmt), {"id": str(user_id), "iid": str(invite_id)})
        await db_session.commit()


async def test_accept_tenant_invite_happy_path(
    http_client: AsyncClient, make_jwt, db_session: AsyncSession
) -> None:
    inviter_id = uuid4()
    user_id = uuid4()
    invite_id = uuid4()
    inviter_email = f"inv-{inviter_id.hex[:8]}@example.com"
    invitee_email = f"tj-{user_id.hex[:8]}@example.com"
    await _insert_auth_user(db_session, inviter_id, inviter_email)
    slug = f"ta-{inviter_id.hex[:8]}"
    await db_session.execute(
        text("INSERT INTO tenants (slug, name, created_by) VALUES (:s, :n, :u)"),
        {"s": slug, "n": "TA", "u": str(inviter_id)},
    )
    tid = (
        await db_session.execute(text("SELECT id FROM tenants WHERE slug = :s"), {"s": slug})
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO tenant_invites "
            "(id, tenant_id, email, role, invited_by, expires_at) "
            "VALUES (:id, :tid, :email, 'editor', :inv, :exp)"
        ),
        {
            "id": str(invite_id),
            "tid": str(tid),
            "email": invitee_email,
            "inv": str(inviter_id),
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
    )
    await _insert_auth_user(db_session, user_id, invitee_email)
    await db_session.commit()
    try:
        token = make_jwt(
            sub=user_id,
            user_metadata={"tenant_invite_id": str(invite_id), "tenant_id": str(tid)},
        )
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "tenant"
        assert body["role"] == "editor"
        assert body["tenant_id"] == str(tid)
        mrole = (
            await db_session.execute(
                text(
                    "SELECT role FROM tenant_memberships " "WHERE tenant_id = :t AND user_id = :u"
                ),
                {"t": str(tid), "u": str(user_id)},
            )
        ).scalar_one()
        assert mrole == "editor"
        acc = (
            await db_session.execute(
                text("SELECT accepted_at FROM tenant_invites WHERE id = :id"),
                {"id": str(invite_id)},
            )
        ).scalar_one()
        assert acc is not None
    finally:
        for stmt in (
            "DELETE FROM tenant_memberships WHERE user_id = :uid",
            "DELETE FROM tenant_invites WHERE id = :iid",
            "DELETE FROM tenants WHERE created_by = :inv",
            "DELETE FROM auth.users WHERE id = :uid",
            "DELETE FROM auth.users WHERE id = :inv",
        ):
            await db_session.execute(
                text(stmt),
                {"uid": str(user_id), "iid": str(invite_id), "inv": str(inviter_id)},
            )
        await db_session.commit()
