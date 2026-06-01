"""Tests for ``GET /api/platform/stats``.

Base gate: ``platform.users.read`` (held by both seeded platform system roles).
Per-metric gates layer on top — ``client_tenants`` needs
``platform.clients.read``, ``recent_activity`` needs ``platform.audit.read``.
A metric the caller can't read comes back ``null``.

The platform metrics (``client_tenants``, ``active_platform_users``) are GLOBAL
counts against the shared managed DB, so absolute assertions would be brittle.
We assert the DELTA after seeding N test rows instead, which is exact and
robust. ``@example.com`` hygiene + session-scoped purge handle teardown.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.audit import write_audit_event
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_auth_user(user_id: UUID, email: str) -> None:
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
                "'authenticated', :email, '', now(), now(), now())"
            ),
            {"id": str(user_id), "email": email},
        )
        await s.commit()


@pytest_asyncio.fixture
async def users_read_only_user() -> AsyncIterator[UUID]:
    """A platform user holding ONLY ``platform.users.read`` (via a custom
    platform role) — passes the base gate but neither ``platform.clients.read``
    nor ``platform.audit.read``, so those two metrics must be ``null``.
    """
    user_id = uuid4()
    role_id = uuid4()
    email = f"pstats-usersonly-{user_id.hex[:8]}@example.com"
    await _seed_auth_user(user_id, email)
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(user_id), "e": email},
        )
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO roles "
                "(id, scope, workspace_id, key, name, description, is_system, created_by) "
                "VALUES (:id, 'platform', NULL, :k, 'UsersOnly', '', false, :cb)"
            ),
            {"id": str(role_id), "k": f"pstats_{role_id.hex[:8]}", "cb": str(user_id)},
        )
        await s.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT :r, id FROM permissions WHERE key = 'platform.users.read'"
            ),
            {"r": str(role_id)},
        )
        await s.execute(
            text(
                "INSERT INTO user_roles (id, auth_user_id, role_id, workspace_id, granted_by) "
                "VALUES (:id, :u, :r, NULL, NULL)"
            ),
            {"id": str(uuid4()), "u": str(user_id), "r": str(role_id)},
        )
        await s.commit()
    yield user_id


async def _get_stats(
    http_client: AsyncClient, make_jwt: Callable[..., str], sub: UUID
) -> dict[str, object]:
    token = make_jwt(sub=sub)
    res = await http_client.get("/api/platform/stats", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    body: dict[str, object] = res.json()
    return body


# --- auth / authz gates ----------------------------------------------------


async def test_stats_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/platform/stats")
    assert res.status_code == 401


async def test_stats_403_for_unprivileged(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """A provisioned user with NO platform grants lacks the base gate → 403."""
    user_id = uuid4()
    email = f"pstats-noperm-{user_id.hex[:8]}@example.com"
    await _seed_auth_user(user_id, email)
    async with SessionLocal() as s:
        s.add(PlatformUser(id=user_id, email=email, role=PlatformRole.EDITOR, is_active=True))
        await s.commit()
    token = make_jwt(sub=user_id)
    res = await http_client.get("/api/platform/stats", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


# --- gating matrix ---------------------------------------------------------


async def test_super_admin_sees_all_metrics(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    """super_admin holds every platform perm → every metric is a non-null int."""
    body = await _get_stats(http_client, make_jwt, existing_super_admin.id)
    assert isinstance(body["client_tenants"], int)
    assert isinstance(body["active_platform_users"], int)
    assert isinstance(body["recent_activity"], int)


async def test_users_read_only_nulls_other_metrics(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    users_read_only_user: UUID,
) -> None:
    """A caller with only ``platform.users.read`` sees that one metric; the
    metrics behind ``platform.clients.read`` / ``platform.audit.read`` are
    ``null``."""
    body = await _get_stats(http_client, make_jwt, users_read_only_user)
    assert isinstance(body["active_platform_users"], int)
    assert body["client_tenants"] is None
    assert body["recent_activity"] is None


# --- count correctness (delta-based on the shared DB) ----------------------


async def test_client_tenants_count_increases_by_seeded(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    """Seeding N tenants raises ``client_tenants`` by exactly N."""
    before = await _get_stats(http_client, make_jwt, existing_super_admin.id)
    base = before["client_tenants"]
    assert isinstance(base, int)

    creator = uuid4()
    await _seed_auth_user(creator, f"pstats-tenant-creator-{creator.hex[:8]}@example.com")
    n = 3
    async with SessionLocal() as s:
        for _ in range(n):
            tid = uuid4()
            await s.execute(
                text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
                {
                    "t": str(tid),
                    "s": f"pstats-{tid.hex[:8]}",
                    "n": "pstats-tenant",
                    "u": str(creator),
                },
            )
        await s.commit()

    after = await _get_stats(http_client, make_jwt, existing_super_admin.id)
    assert after["client_tenants"] == base + n


async def test_recent_activity_count_increases_by_seeded(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    """Seeding N platform-scope audit events raises ``recent_activity`` by N."""
    before = await _get_stats(http_client, make_jwt, existing_super_admin.id)
    base = before["recent_activity"]
    assert isinstance(base, int)

    actor = uuid4()
    await _seed_auth_user(actor, f"pstats-activity-{actor.hex[:8]}@example.com")
    n = 2
    async with SessionLocal() as s:
        for i in range(n):
            await write_audit_event(
                s,
                actor_id=actor,
                action=f"test_pstats_activity.{i}",
                target_type="role",
                target_id=uuid4(),
                scope="platform",
            )
        await s.commit()

    after = await _get_stats(http_client, make_jwt, existing_super_admin.id)
    assert after["recent_activity"] == base + n
