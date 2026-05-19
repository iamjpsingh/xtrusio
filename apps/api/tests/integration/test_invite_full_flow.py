"""Owner creates a tenant invite -> invitee 'clicks the email' (we simulate Supabase
adding the user with the right metadata) -> /invites/accept -> /me reflects new role."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_owner_invites_admin_full_flow(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt,
    mock_supabase_admin: MagicMock,
) -> None:
    # 1. Seed an owner with a tenant.
    owner_id = uuid4()
    email_owner = f"owner-{owner_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(owner_id), "email": email_owner},
    )
    await db_session.execute(
        text("INSERT INTO tenants (slug, name, created_by) VALUES (:s, 'T', :u)"),
        {"s": f"t-{owner_id.hex[:8]}", "u": str(owner_id)},
    )
    tid = (
        await db_session.execute(
            text("SELECT id FROM tenants WHERE slug = :s"),
            {"s": f"t-{owner_id.hex[:8]}"},
        )
    ).scalar_one()
    # Synthetic tenant created outside onboarding: seed its 4 workspace system
    # roles + wire their role_permissions (the precondition every real tenant
    # satisfies via the reconciler). Under P3b the owner's authz to create an
    # invite is resolver-driven, so the owner also needs the workspace `owner`
    # user_roles grant. Invite-acceptance writes the invitee's grant.
    from xtrusio_api.rbac.grants import grant_role
    from xtrusio_api.rbac.reconcile import wire_workspace_role_perms

    await db_session.execute(
        text(
            "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
            "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
            "('owner'),('admin'),('editor'),('read_only')) AS v(key)"
        ),
        {"t": str(tid)},
    )
    await wire_workspace_role_perms(db_session, workspace_id=tid)
    await db_session.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
            "VALUES (:tid, :uid, 'owner')"
        ),
        {"tid": str(tid), "uid": str(owner_id)},
    )
    await grant_role(
        db_session, auth_user_id=owner_id, scope="workspace", key="owner", workspace_id=tid
    )
    await db_session.commit()

    # 2. Owner creates an invite.
    owner_token = make_jwt(sub=owner_id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
    invitee_email = f"new-{uuid4().hex[:8]}@example.com"
    r = await http_client.post(
        f"/api/tenants/{tid}/invites",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": invitee_email, "role": "admin"},
    )
    assert r.status_code == 201
    invite_id = r.json()["id"]

    # 3. Simulate Supabase creating the user + delivering them to /accept-invite.
    invitee_id = uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(invitee_id), "email": invitee_email},
    )
    await db_session.commit()
    try:
        # 4. Invitee accepts.
        token = make_jwt(
            sub=invitee_id,
            user_metadata={
                "tenant_invite_id": invite_id,
                "tenant_id": str(tid),
                "tenant_role": "admin",
            },
        )
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "tenant"
        assert body["role"] == "admin"

        # 5. /me reflects admin role.
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        body = r.json()
        assert len(body["tenants"]) == 1
        assert body["tenants"][0]["role"] == "admin"
    finally:
        for stmt in (
            "DELETE FROM user_roles WHERE auth_user_id IN (:o, :i)",
            "DELETE FROM tenant_invites WHERE id = :iid",
            "DELETE FROM tenant_memberships WHERE tenant_id = :tid",
            "DELETE FROM roles WHERE workspace_id = :tid",
            "DELETE FROM tenants WHERE id = :tid",
            "DELETE FROM auth.users WHERE id = :o",
            "DELETE FROM auth.users WHERE id = :i",
        ):
            await db_session.execute(
                text(stmt),
                {
                    "iid": invite_id,
                    "tid": str(tid),
                    "o": str(owner_id),
                    "i": str(invitee_id),
                },
            )
        await db_session.commit()
