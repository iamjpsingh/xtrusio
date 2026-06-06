"""Audit-coverage backfill (Slice A2): every backfilled mutation lands its
audit row in the SAME transaction as the mutation.

One test per backfilled service fn asserts the row's action / scope /
workspace_id / actor / payload keys. Service-layer (not route) so each test is
focused + fast; ephemeral @example.com principals with FK-safe teardown, no
super_admin creation (the provision/settings tests use the read-only
``existing_super_admin`` fixture as actor where a privileged actor is required).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser
from xtrusio_api.models.tenant_membership import TenantRole
from xtrusio_api.services.invite_acceptance import _accept_platform, _accept_tenant
from xtrusio_api.services.onboarding import create_tenant_with_owner
from xtrusio_api.services.platform_invites import create_platform_invite, revoke_platform_invite
from xtrusio_api.services.platform_settings import update_settings
from xtrusio_api.services.platform_user_provision import create_platform_user
from xtrusio_api.services.tenant_invites import create_tenant_invite, revoke_tenant_invite

pytestmark = pytest.mark.asyncio(loop_scope="session")


# --- helpers ---------------------------------------------------------------


async def _seed_auth_user(label: str) -> UUID:
    uid = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": f"audc-{label}-{uid.hex[:8]}@example.com"},
        )
        await s.commit()
    return uid


async def _drop_auth_user(uid: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :u"), {"u": str(uid)}
        )
        await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(uid)})
        await s.commit()


async def _seed_tenant_with_owner() -> tuple[UUID, UUID]:
    """Tenant + owner membership + a SCOPED owner user_roles grant so the owner
    holds the workspace owner perms (needed for the tenant-invite perm checks).

    Uses ``grant_role`` for just this owner — NOT the global
    ``reconcile_user_roles_from_enums`` — so the seed can't trip on unrelated
    orphaned memberships left in the shared managed DB by other tests.
    """
    from xtrusio_api.rbac.grants import grant_role
    from xtrusio_api.rbac.reconcile import wire_workspace_role_perms

    uid, tid = uuid4(), uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": f"audc-owner-{uid.hex[:8]}@example.com"},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"audc-{tid.hex[:8]}", "n": "audc tenant", "u": str(uid)},
        )
        # That tenant's 4 workspace system roles (mirrors onboarding).
        await s.execute(
            text(
                "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
                "SELECT 'workspace', :t, v.key, v.name, '', true FROM (VALUES "
                "('owner','Owner'),('admin','Admin'),('editor','Editor'),"
                "('read_only','Read Only')) AS v(key, name)"
            ),
            {"t": str(tid)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        # Wire this workspace's role_permissions + grant the owner (scoped) in
        # the same tx. granted_by stays NULL so the 0013 priv-escalation trigger
        # is bypassed (matches onboarding's seed path).
        await wire_workspace_role_perms(s, workspace_id=tid)
        await grant_role(s, auth_user_id=uid, scope="workspace", key="owner", workspace_id=tid)
        await s.commit()
    return tid, uid


async def _drop_tenant(tid: UUID, owner_id: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("DELETE FROM rbac_audit_log WHERE workspace_id = :t"), {"t": str(tid)})
        await s.execute(text("DELETE FROM tenant_invites WHERE tenant_id = :t"), {"t": str(tid)})
        await s.execute(
            text("DELETE FROM tenant_memberships WHERE tenant_id = :t"), {"t": str(tid)}
        )
        await s.execute(text("DELETE FROM user_roles WHERE workspace_id = :t"), {"t": str(tid)})
        await s.execute(
            text(
                "DELETE FROM role_permissions WHERE role_id IN "
                "(SELECT id FROM roles WHERE workspace_id = :t)"
            ),
            {"t": str(tid)},
        )
        await s.execute(text("DELETE FROM roles WHERE workspace_id = :t"), {"t": str(tid)})
        await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tid)})
        await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(owner_id)})
        await s.commit()


async def _audit_row(db: AsyncSession, *, target_id: Any, action: str) -> dict[str, Any]:
    row = (
        (
            await db.execute(
                text(
                    "SELECT actor_auth_user_id, action, target_type, target_id, scope, "
                    "workspace_id, before, after FROM rbac_audit_log "
                    "WHERE target_id = :tid AND action = :a"
                ),
                {"tid": str(target_id), "a": action},
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


# --- platform invites ------------------------------------------------------


async def test_create_platform_invite_audits() -> None:
    actor = await _seed_auth_user("pinv-create")
    email = f"audc-invitee-{uuid4().hex[:8]}@example.com"
    invite_id: UUID | None = None
    try:
        async with SessionLocal() as s:
            invite = await create_platform_invite(
                s, email=email, role=PlatformRole.ADMIN, invited_by=actor
            )
            invite_id = invite.id
            await s.commit()
        async with SessionLocal() as s:
            row = await _audit_row(s, target_id=invite_id, action="platform_invite.create")
        assert UUID(str(row["actor_auth_user_id"])) == actor
        assert row["scope"] == "platform"
        assert row["target_type"] == "invite"
        assert row["workspace_id"] is None
        assert row["after"] == {"email": email, "role": "admin"}
    finally:
        if invite_id is not None:
            async with SessionLocal() as s:
                await s.execute(
                    text("DELETE FROM invite_email_outbox WHERE payload->>'email' = :e"),
                    {"e": email},
                )
                await s.execute(
                    text("DELETE FROM platform_invites WHERE id = :i"), {"i": str(invite_id)}
                )
                await s.commit()
        await _drop_auth_user(actor)


async def test_revoke_platform_invite_audits() -> None:
    actor = await _seed_auth_user("pinv-revoke")
    email = f"audc-rev-{uuid4().hex[:8]}@example.com"
    invite_id = uuid4()
    try:
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO platform_invites "
                    "(id, email, role, invited_by, expires_at) "
                    "VALUES (:id, :e, 'admin', :inv, :exp)"
                ),
                {
                    "id": str(invite_id),
                    "e": email,
                    "inv": str(actor),
                    "exp": datetime.now(UTC) + timedelta(days=7),
                },
            )
            await s.commit()
        # revoke_platform_invite self-commits; pass the route's caller as actor.
        async with SessionLocal() as s:
            await revoke_platform_invite(s, invite_id=invite_id, actor_id=actor)
        async with SessionLocal() as s:
            row = await _audit_row(s, target_id=invite_id, action="platform_invite.revoke")
        assert UUID(str(row["actor_auth_user_id"])) == actor
        assert row["scope"] == "platform"
        assert row["before"] == {"email": email, "role": "admin"}
        # invite was actually marked revoked
        async with SessionLocal() as s:
            revoked = (
                await s.execute(
                    text("SELECT revoked_at FROM platform_invites WHERE id = :i"),
                    {"i": str(invite_id)},
                )
            ).scalar_one()
        assert revoked is not None
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM platform_invites WHERE id = :i"), {"i": str(invite_id)}
            )
            await s.commit()
        await _drop_auth_user(actor)


# --- tenant invites --------------------------------------------------------


async def test_create_tenant_invite_audits() -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    email = f"audc-tinv-{uuid4().hex[:8]}@example.com"
    invite_id: UUID | None = None
    try:
        async with SessionLocal() as s:
            invite = await create_tenant_invite(
                s, tenant_id=tid, inviter_id=owner_id, email=email, role=TenantRole.EDITOR
            )
            invite_id = invite.id
            await s.commit()
        async with SessionLocal() as s:
            row = await _audit_row(s, target_id=invite_id, action="tenant_invite.create")
        assert UUID(str(row["actor_auth_user_id"])) == owner_id
        assert row["scope"] == "workspace"
        assert UUID(str(row["workspace_id"])) == tid
        assert row["after"] == {"email": email, "role": "editor"}
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM invite_email_outbox WHERE payload->>'email' = :e"),
                {"e": email},
            )
            await s.commit()
        await _drop_tenant(tid, owner_id)


async def test_revoke_tenant_invite_audits() -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    email = f"audc-trev-{uuid4().hex[:8]}@example.com"
    invite_id = uuid4()
    try:
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO tenant_invites "
                    "(id, tenant_id, email, role, invited_by, expires_at) "
                    "VALUES (:id, :t, :e, 'editor', :inv, :exp)"
                ),
                {
                    "id": str(invite_id),
                    "t": str(tid),
                    "e": email,
                    "inv": str(owner_id),
                    "exp": datetime.now(UTC) + timedelta(days=7),
                },
            )
            await s.commit()
        # revoke_tenant_invite self-commits; requester_id is the actor.
        async with SessionLocal() as s:
            await revoke_tenant_invite(s, tenant_id=tid, invite_id=invite_id, requester_id=owner_id)
        async with SessionLocal() as s:
            row = await _audit_row(s, target_id=invite_id, action="tenant_invite.revoke")
        assert UUID(str(row["actor_auth_user_id"])) == owner_id
        assert row["scope"] == "workspace"
        assert UUID(str(row["workspace_id"])) == tid
        assert row["before"] == {"email": email, "role": "editor"}
    finally:
        await _drop_tenant(tid, owner_id)


# --- invite acceptance -----------------------------------------------------


async def test_accept_platform_invite_audits() -> None:
    uid = uuid4()
    invite_id = uuid4()
    email = f"audc-acc-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO platform_invites (id, email, role, invited_by, expires_at) "
                "VALUES (:id, :e, 'admin', :inv, :exp)"
            ),
            {
                "id": str(invite_id),
                "e": email,
                "inv": str(uid),
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        await s.commit()
    try:
        async with SessionLocal() as s:
            await _accept_platform(s, user_id=uid, email=email, invite_id=invite_id)
            await s.commit()
        async with SessionLocal() as s:
            row = await _audit_row(s, target_id=invite_id, action="platform_invite.accept")
        assert UUID(str(row["actor_auth_user_id"])) == uid
        assert row["scope"] == "platform"
        assert row["after"] == {"email": email, "role": "admin"}
    finally:
        async with SessionLocal() as s:
            await s.execute(text("DELETE FROM user_roles WHERE auth_user_id = :u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM platform_users WHERE id = :u"), {"u": str(uid)})
            await s.execute(
                text("DELETE FROM platform_invites WHERE id = :i"), {"i": str(invite_id)}
            )
            await s.execute(
                text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :u"), {"u": str(uid)}
            )
            await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(uid)})
            await s.commit()


async def test_accept_tenant_invite_audits() -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    member = uuid4()
    invite_id = uuid4()
    email = f"audc-tacc-{member.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(member), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_invites (id, tenant_id, email, role, invited_by, expires_at) "
                "VALUES (:id, :t, :e, 'editor', :inv, :exp)"
            ),
            {
                "id": str(invite_id),
                "t": str(tid),
                "e": email,
                "inv": str(owner_id),
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        await s.commit()
    try:
        async with SessionLocal() as s:
            await _accept_tenant(s, user_id=member, email=email, invite_id=invite_id)
            await s.commit()
        async with SessionLocal() as s:
            row = await _audit_row(s, target_id=invite_id, action="tenant_invite.accept")
        assert UUID(str(row["actor_auth_user_id"])) == member
        assert row["scope"] == "workspace"
        assert UUID(str(row["workspace_id"])) == tid
        assert row["after"] == {"email": email, "role": "editor"}
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM user_roles WHERE auth_user_id = :u"), {"u": str(member)}
            )
            await s.execute(
                text("DELETE FROM tenant_memberships WHERE user_id = :u"), {"u": str(member)}
            )
            await s.execute(text("DELETE FROM tenant_invites WHERE id = :i"), {"i": str(invite_id)})
            await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(member)})
            await s.commit()
        await _drop_tenant(tid, owner_id)


# --- onboarding ------------------------------------------------------------


async def test_onboarding_create_tenant_audits() -> None:
    uid = await _seed_auth_user("onb")
    tid: UUID | None = None
    try:
        async with SessionLocal() as s:
            tenant = await create_tenant_with_owner(s, user_id=uid, workspace_name="Audc Onboard")
            tid = tenant.id
            await s.commit()
        async with SessionLocal() as s:
            row = await _audit_row(s, target_id=tid, action="tenant.create")
        assert UUID(str(row["actor_auth_user_id"])) == uid
        assert row["scope"] == "workspace"
        assert UUID(str(row["workspace_id"])) == tid
        assert row["target_type"] == "tenant"
        assert set(row["after"].keys()) == {"slug", "name"}
        assert row["after"]["name"] == "Audc Onboard"
    finally:
        if tid is not None:
            await _drop_tenant(tid, uid)
        else:
            await _drop_auth_user(uid)


# --- platform user provision -----------------------------------------------


async def test_create_platform_user_audits(
    existing_super_admin: PlatformUser, mock_supabase_admin: Any
) -> None:
    new_uid = uuid4()
    email = f"audc-prov-{new_uid.hex[:8]}@example.com"
    # The supabase admin mock returns a created user with our chosen id.
    created_user = type("U", (), {"id": str(new_uid)})()
    mock_supabase_admin.auth.admin.create_user.return_value = type(
        "R", (), {"user": created_user}
    )()
    # The mocked Admin API does NOT persist auth.users; seed the row the real
    # ``create_user`` would write, so the user_roles.auth_user_id FK resolves.
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(new_uid), "e": email},
        )
        await s.commit()
    try:
        async with SessionLocal() as s:
            await create_platform_user(
                s, actor_id=existing_super_admin.id, email=email, password="x-Secret-123!"
            )
            await s.commit()
        async with SessionLocal() as s:
            row = await _audit_row(s, target_id=new_uid, action="platform_user.create")
        assert UUID(str(row["actor_auth_user_id"])) == existing_super_admin.id
        assert row["scope"] == "platform"
        assert row["target_type"] == "platform_user"
        assert row["after"] == {"email": email, "role": "admin"}
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM user_roles WHERE auth_user_id = :u"), {"u": str(new_uid)}
            )
            await s.execute(text("DELETE FROM platform_users WHERE id = :u"), {"u": str(new_uid)})
            await s.execute(
                text("DELETE FROM rbac_audit_log WHERE target_id = :u"), {"u": str(new_uid)}
            )
            await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(new_uid)})
            await s.commit()


# --- platform settings -----------------------------------------------------


async def test_update_settings_audits(existing_super_admin: PlatformUser) -> None:
    # The autouse _isolate_platform_settings fixture restores the singleton
    # after the test, so flipping the flag here is safe.
    async with SessionLocal() as s:
        current = (
            await s.execute(text("SELECT signups_enabled FROM platform_settings WHERE id = 1"))
        ).scalar_one()
    new_value = not current
    try:
        async with SessionLocal() as s:
            await update_settings(s, signups_enabled=new_value, updated_by=existing_super_admin.id)
            await s.commit()
        async with SessionLocal() as s:
            row = await _audit_row(s, target_id="1", action="platform.settings.updated")
        assert UUID(str(row["actor_auth_user_id"])) == existing_super_admin.id
        assert row["scope"] == "platform"
        assert row["target_type"] == "platform_settings"
        assert row["before"] == {"signups_enabled": current}
        assert row["after"] == {"signups_enabled": new_value}
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "DELETE FROM rbac_audit_log WHERE action = 'platform.settings.updated' "
                    "AND actor_auth_user_id = :u"
                ),
                {"u": str(existing_super_admin.id)},
            )
            await s.commit()
