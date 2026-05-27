"""PAR-A C2: invite acceptance reads from app_metadata, not user_metadata.

The core regression: pre-PAR-A, an invitee could forge ``platform_invite_id``
in their own ``user_metadata`` (writable from the user's own access token via
``PUT /auth/v1/user``) and self-accept a fabricated invite. C2 moves the
claim to ``app_metadata`` (service-role-only writable).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _insert_auth_user(db: AsyncSession, user_id: UUID, email: str) -> None:
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )


async def _seed_pending_platform_invite(db: AsyncSession, *, invited_by: UUID, email: str) -> UUID:
    iid = uuid4()
    await db.execute(
        text(
            "INSERT INTO platform_invites "
            "(id, email, role, invited_by, expires_at, accepted_at, revoked_at) "
            "VALUES (:id, :email, 'admin', :inv, :exp, NULL, NULL)"
        ),
        {
            "id": str(iid),
            "email": email,
            "inv": str(invited_by),
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
    )
    return iid


async def test_invite_id_only_in_user_metadata_is_rejected(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    db_session: AsyncSession,
) -> None:
    """Forge ``platform_invite_id`` in ``user_metadata`` (the writable claim)
    only. The acceptance route reads from ``app_metadata`` (C2), so the forge
    is invisible — ``no_invite``."""
    invitee_id = uuid4()
    email = f"forge-{invitee_id.hex[:8]}@example.com"
    invite_id = await _seed_pending_platform_invite(
        db_session, invited_by=existing_super_admin.id, email=email
    )
    await _insert_auth_user(db_session, invitee_id, email)
    await db_session.commit()
    try:
        # platform_invite_id forged in user_metadata; app_metadata stays empty.
        forged = make_jwt(
            sub=invitee_id,
            user_metadata={"platform_invite_id": str(invite_id), "platform_role": "admin"},
            app_metadata={},
        )
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {forged}"}
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "no_invite"
        # Confirm: the invite remained PENDING (not accepted).
        row = (
            await db_session.execute(
                text("SELECT accepted_at FROM platform_invites WHERE id = :id"),
                {"id": str(invite_id)},
            )
        ).scalar_one()
        assert row is None
    finally:
        for stmt in (
            "DELETE FROM platform_users WHERE id = :u",
            "DELETE FROM platform_invites WHERE id = :i",
            "DELETE FROM auth.users WHERE id = :u",
        ):
            await db_session.execute(text(stmt), {"u": str(invitee_id), "i": str(invite_id)})
        await db_session.commit()


async def test_invite_id_in_app_metadata_is_accepted(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    db_session: AsyncSession,
) -> None:
    """Legitimate path: the same invite, but with the invite id in
    ``app_metadata`` (where the admin API placed it) — 200, accepted."""
    invitee_id = uuid4()
    email = f"legit-{invitee_id.hex[:8]}@example.com"
    invite_id = await _seed_pending_platform_invite(
        db_session, invited_by=existing_super_admin.id, email=email
    )
    await _insert_auth_user(db_session, invitee_id, email)
    await db_session.commit()
    try:
        ok = make_jwt(
            sub=invitee_id,
            app_metadata={"platform_invite_id": str(invite_id), "platform_role": "admin"},
        )
        r = await http_client.post("/api/invites/accept", headers={"Authorization": f"Bearer {ok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "platform"
        assert body["role"] == "admin"
        row = (
            await db_session.execute(
                text("SELECT accepted_at FROM platform_invites WHERE id = :id"),
                {"id": str(invite_id)},
            )
        ).scalar_one()
        assert row is not None
    finally:
        for stmt in (
            "DELETE FROM user_roles WHERE auth_user_id = :u",
            "DELETE FROM platform_users WHERE id = :u",
            "DELETE FROM platform_invites WHERE id = :i",
            "DELETE FROM auth.users WHERE id = :u",
        ):
            await db_session.execute(text(stmt), {"u": str(invitee_id), "i": str(invite_id)})
        await db_session.commit()


async def test_invite_id_in_both_metadata_uses_app_metadata(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    db_session: AsyncSession,
) -> None:
    """Forge ``user_metadata`` to point at invite B; ``app_metadata`` points
    at invite A (the legit one). Acceptance must follow ``app_metadata``."""
    invitee_id = uuid4()
    email = f"both-{invitee_id.hex[:8]}@example.com"
    legit_iid = await _seed_pending_platform_invite(
        db_session, invited_by=existing_super_admin.id, email=email
    )
    # A second, unrelated pending invite for a different email — the attacker
    # tries to swap onto this in user_metadata.
    decoy_iid = await _seed_pending_platform_invite(
        db_session, invited_by=existing_super_admin.id, email=f"decoy-{uuid4().hex[:8]}@example.com"
    )
    await _insert_auth_user(db_session, invitee_id, email)
    await db_session.commit()
    try:
        token = make_jwt(
            sub=invitee_id,
            user_metadata={"platform_invite_id": str(decoy_iid)},  # forged
            app_metadata={"platform_invite_id": str(legit_iid), "platform_role": "admin"},
        )
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        # The legit invite (app_metadata) is accepted; the decoy is left alone.
        assert r.status_code == 200
        decoy_row = (
            await db_session.execute(
                text("SELECT accepted_at FROM platform_invites WHERE id = :id"),
                {"id": str(decoy_iid)},
            )
        ).scalar_one()
        assert decoy_row is None
        legit_row = (
            await db_session.execute(
                text("SELECT accepted_at FROM platform_invites WHERE id = :id"),
                {"id": str(legit_iid)},
            )
        ).scalar_one()
        assert legit_row is not None
    finally:
        for stmt in (
            "DELETE FROM user_roles WHERE auth_user_id = :u",
            "DELETE FROM platform_users WHERE id = :u",
            "DELETE FROM platform_invites WHERE id = :i1 OR id = :i2",
            "DELETE FROM auth.users WHERE id = :u",
        ):
            await db_session.execute(
                text(stmt),
                {"u": str(invitee_id), "i1": str(legit_iid), "i2": str(decoy_iid)},
            )
        await db_session.commit()
