"""PAR-A M22: PrivilegeEscalationError 403 body is the bare constant.

The missing perm key MUST stay server-side only (logged via structlog at
WARN level, not returned to the client). Returning it lets an attacker walk
the RBAC graph by attempting escalations and reading the responses.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


# Shared helper shapes mirror those in test_platform_role_grants.py so the
# privilege-escalation cycle is exercised the same way real routes hit it.


async def _create_example_platform_user() -> UUID:
    uid = uuid4()
    email = f"pesc-{uid.hex[:8]}@example.com"
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
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, :r, true)"
            ),
            {"id": str(uid), "e": email, "r": PlatformRole.EDITOR.value},
        )
        await s.commit()
    return uid


async def _seed_roles_manage_only_grant(user_id: UUID) -> tuple[UUID, UUID]:
    """Grant ``user_id`` a custom platform role holding ONLY
    ``platform.roles.manage`` (granted_by NULL bypasses the priv-escalation
    trigger). This lets the role-create/PATCH route gate pass while the actor
    still lacks ``platform.clients.manage``. Returns (grant_id, role_id)."""
    role_id = uuid4()
    key = f"pesc_rm_{role_id.hex[:8]}"
    grant_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO roles "
                "(id, scope, workspace_id, key, name, description, is_system) "
                "VALUES (:id, 'platform', NULL, :k, 'PEsc RolesMgr', '', false)"
            ),
            {"id": str(role_id), "k": key},
        )
        await s.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT :r, id FROM permissions WHERE key = 'platform.roles.manage'"
            ),
            {"r": str(role_id)},
        )
        await s.execute(
            text(
                "INSERT INTO user_roles (id, auth_user_id, role_id, workspace_id, granted_by) "
                "VALUES (:id, :u, :r, NULL, NULL)"
            ),
            {"id": str(grant_id), "u": str(user_id), "r": str(role_id)},
        )
        await s.commit()
    return grant_id, role_id


async def _platform_admin_role_id() -> UUID:
    async with SessionLocal() as s:
        rid = (
            await s.execute(
                text(
                    "SELECT id FROM roles WHERE scope='platform' "
                    "AND workspace_id IS NULL AND key='admin' AND is_system"
                )
            )
        ).scalar_one()
        return UUID(str(rid))


async def _seed_admin_grant(user_id: UUID) -> UUID:
    """System-level seed (granted_by = NULL bypasses the priv-escalation
    trigger; this is how the test sets up the actor's starting role)."""
    admin_role_id = await _platform_admin_role_id()
    grant_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO user_roles (id, auth_user_id, role_id, workspace_id, granted_by) "
                "VALUES (:id, :u, :r, NULL, NULL)"
            ),
            {"id": str(grant_id), "u": str(user_id), "r": str(admin_role_id)},
        )
        await s.commit()
    return grant_id


async def _create_custom_platform_role(*, creator_id: UUID, permission_keys: list[str]) -> UUID:
    role_id = uuid4()
    key = f"pesc_custom_{role_id.hex[:8]}"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO roles "
                "(id, scope, workspace_id, key, name, description, is_system, created_by) "
                "VALUES (:id, 'platform', NULL, :k, 'PEsc', '', false, :cb)"
            ),
            {"id": str(role_id), "k": key, "cb": str(creator_id)},
        )
        for pk in permission_keys:
            await s.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT :r, id FROM permissions WHERE key = :k"
                ),
                {"r": str(role_id), "k": pk},
            )
        await s.commit()
    return role_id


async def _cleanup_user(user_id: UUID) -> None:
    async with SessionLocal() as s:
        # actor_auth_user_id is uuid; target_id is text — separate stmts so
        # the parameter types align with each column's actual type.
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :u"),
            {"u": str(user_id)},
        )
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE target_id = :u"),
            {"u": str(user_id)},
        )
        await s.execute(
            text("DELETE FROM user_roles WHERE auth_user_id = :u OR granted_by = :u"),
            {"u": str(user_id)},
        )
        await s.execute(text("DELETE FROM platform_users WHERE id = :u"), {"u": str(user_id)})
        await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(user_id)})
        await s.commit()


async def _cleanup_role(role_id: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text("DELETE FROM rbac_audit_log WHERE target_id = :id"), {"id": str(role_id)}
        )
        await s.execute(text("DELETE FROM user_roles WHERE role_id = :id"), {"id": str(role_id)})
        await s.execute(
            text("DELETE FROM role_permissions WHERE role_id = :id"), {"id": str(role_id)}
        )
        await s.execute(
            text("DELETE FROM roles WHERE id = :id AND NOT is_system"), {"id": str(role_id)}
        )
        await s.commit()


async def _cleanup_grant(grant_id: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("DELETE FROM user_roles WHERE id = :id"), {"id": str(grant_id)})
        await s.commit()


async def test_platform_grant_403_body_is_bare_constant(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    """Actor holds platform admin (=> ``platform.users.manage`` so route
    gate passes), tries to grant a role containing ``platform.roles.manage``
    (which admin doesn't hold). Service raises PrivilegeEscalationError;
    route must respond with the bare constant ``"privilege_escalation"``."""
    actor_id = await _create_example_platform_user()
    actor_grant_id = await _seed_admin_grant(actor_id)
    custom_role_id = await _create_custom_platform_role(
        creator_id=existing_super_admin.id, permission_keys=["platform.roles.manage"]
    )
    target = await _create_example_platform_user()
    try:
        token = make_jwt(sub=actor_id)
        res = await http_client.post(
            f"/api/platform/users/{target}/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={"role_id": str(custom_role_id)},
        )
        assert res.status_code == 403
        body = res.json()
        # EXACT match — no perm key smuggled in.
        assert body["detail"] == "privilege_escalation"
        # Belt-and-braces: no perm-shaped substring anywhere in the body.
        flat = str(body)
        assert "platform.roles.manage" not in flat
        assert not re.search(r"platform\.[a-z._]+", flat.replace("privilege_escalation", ""))
    finally:
        await _cleanup_grant(actor_grant_id)
        await _cleanup_role(custom_role_id)
        await _cleanup_user(actor_id)
        await _cleanup_user(target)


async def test_platform_role_create_403_body_is_bare_constant(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
) -> None:
    """Role-DEFINITION escalation path: actor holds only ``platform.roles.manage``
    (so the POST /roles gate passes), tries to CREATE a role containing
    ``platform.clients.manage`` (which they don't hold). Service raises
    PrivilegeEscalationError; the route must respond with the bare constant
    ``"privilege_escalation"`` — no perm key smuggled into the body."""
    actor_id = await _create_example_platform_user()
    actor_grant_id, actor_role_id = await _seed_roles_manage_only_grant(actor_id)
    created_key = f"pesc_attempt_{uuid4().hex[:8]}"
    try:
        token = make_jwt(sub=actor_id)
        res = await http_client.post(
            "/api/platform/roles",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "key": created_key,
                "name": "escalation attempt",
                "description": None,
                "permission_keys": ["platform.clients.manage"],
            },
        )
        assert res.status_code == 403
        body = res.json()
        assert body["detail"] == "privilege_escalation"
        flat = str(body)
        assert "platform.clients.manage" not in flat
        assert not re.search(r"platform\.[a-z._]+", flat.replace("privilege_escalation", ""))
    finally:
        # The escalation role was never created (403); clean up any stray row by
        # key, then the actor's seed role + the actor.
        async with SessionLocal() as s:
            await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
            await s.execute(
                text("DELETE FROM roles WHERE key = :k AND NOT is_system"),
                {"k": created_key},
            )
            await s.commit()
        await _cleanup_grant(actor_grant_id)
        await _cleanup_role(actor_role_id)
        await _cleanup_user(actor_id)
