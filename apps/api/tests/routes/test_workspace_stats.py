"""Tests for ``GET /api/workspaces/{workspace_id}/stats``.

Base gate: ``workspace.members.read`` (held by every tenant role). Per-metric
gates layer on top — ``members`` and ``pending_invites`` ride that same
``workspace.members.read``, while ``recent_activity`` needs
``workspace.audit.read`` (owner / workspace_admin only). A metric the caller
can't read comes back ``null`` — so a ``read_only`` member sees members +
pending invites but NOT recent activity.

Counts are workspace-scoped (filtered by ``:wid``), so a freshly provisioned
workspace gives exact, isolated numbers. We still assert the DELTA after seeding
N rows (robust against any incidental activity). ``@example.com`` hygiene +
session-scoped purge handle teardown.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.audit import write_audit_event
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _provision_owner_workspace(
    member_role: str = "read_only", *, platform_user: bool = True
) -> tuple[UUID, UUID, UUID]:
    """Seed (workspace, owner_id, member_id). Owner holds every workspace perm;
    the member holds whatever ``member_role`` implies (``read_only`` →
    ``workspace.members.read`` + ``workspace.settings.read``, but NOT
    ``workspace.audit.read``).

    ``platform_user=False`` reproduces a REAL client: a tenant member with NO
    ``platform_users`` row (platform users = super_admin only, #63). Workspace
    endpoints must accept them — auth is `require_authenticated` (auth.users),
    authz is `require_permission(workspace_id)` — NOT a platform_users check."""
    owner_id, tid, member_id = uuid4(), uuid4(), uuid4()
    o_email = f"wstats-owner-{owner_id.hex[:8]}@example.com"
    m_email = f"wstats-mem-{member_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        for uid, email in ((owner_id, o_email), (member_id, m_email)):
            await s.execute(
                text(
                    "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                    "encrypted_password, email_confirmed_at, created_at, updated_at) "
                    "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                    "'authenticated',:e,'',now(),now(),now())"
                ),
                {"id": str(uid), "e": email},
            )
            if platform_user:
                await s.execute(
                    text(
                        "INSERT INTO platform_users (id, email, role, is_active) "
                        "VALUES (:id, :e, 'editor', true)"
                    ),
                    {"id": str(uid), "e": email},
                )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"wstats-{tid.hex[:8]}", "n": "ws-stats", "u": str(owner_id)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :o, 'owner'), (:t, :m, :r)"
            ),
            {"t": str(tid), "o": str(owner_id), "m": str(member_id), "r": member_role},
        )
        await s.commit()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return tid, owner_id, member_id


async def _seed_non_member(label: str) -> UUID:
    uid = uuid4()
    email = f"{label}-{uid.hex[:8]}@example.com"
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
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(uid), "e": email},
        )
        await s.commit()
    return uid


async def _get_stats(
    http_client: AsyncClient, make_jwt: Callable[..., str], sub: UUID, tid: UUID
) -> dict[str, object]:
    token = make_jwt(sub=sub)
    res = await http_client.get(
        f"/api/workspaces/{tid}/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    body: dict[str, object] = res.json()
    return body


# --- auth / authz gates ----------------------------------------------------


async def test_stats_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get(f"/api/workspaces/{uuid4()}/stats")
    assert res.status_code == 401


async def test_workspace_owner_without_platform_user_can_read_stats(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Regression (real client): a workspace owner has a tenant_memberships row
    but NO platform_users row. They must be able to read their own workspace.
    Before the fix, the route's `get_current_user` dependency required a
    platform_users row → 401 'user not provisioned' on EVERY workspace endpoint.
    The gate must be `require_authenticated` + `require_permission(workspace_id)`."""
    tid, owner_id, _member = await _provision_owner_workspace(platform_user=False)
    token = make_jwt(sub=owner_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["members"], int)


async def test_stats_403_for_non_member(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """A provisioned user who is not a member of the workspace lacks the base
    gate → 403."""
    tid, _owner, _member = await _provision_owner_workspace()
    outsider = await _seed_non_member("wstats-outsider")
    token = make_jwt(sub=outsider)
    res = await http_client.get(
        f"/api/workspaces/{tid}/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


# --- gating matrix ---------------------------------------------------------


async def test_owner_sees_all_metrics(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """The owner holds every workspace perm → all three metrics are ints."""
    tid, owner_id, _member = await _provision_owner_workspace()
    body = await _get_stats(http_client, make_jwt, owner_id, tid)
    assert isinstance(body["members"], int)
    assert isinstance(body["pending_invites"], int)
    assert isinstance(body["recent_activity"], int)


async def test_read_only_member_nulls_recent_activity(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """A read_only member holds workspace.members.read but NOT
    workspace.audit.read → members + pending_invites are ints, recent_activity
    is null."""
    tid, _owner, member_id = await _provision_owner_workspace(member_role="read_only")
    body = await _get_stats(http_client, make_jwt, member_id, tid)
    assert isinstance(body["members"], int)
    assert isinstance(body["pending_invites"], int)
    assert body["recent_activity"] is None


# --- count correctness (delta-based, workspace-scoped) ---------------------


async def test_members_count_increases_by_seeded(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Adding N memberships to THIS workspace raises ``members`` by exactly N
    (and never leaks another workspace's members)."""
    tid, owner_id, _member = await _provision_owner_workspace()
    before = await _get_stats(http_client, make_jwt, owner_id, tid)
    base = before["members"]
    assert isinstance(base, int)

    n = 3
    async with SessionLocal() as s:
        for _ in range(n):
            uid = uuid4()
            await s.execute(
                text(
                    "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                    "encrypted_password, email_confirmed_at, created_at, updated_at) "
                    "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                    "'authenticated',:e,'',now(),now(),now())"
                ),
                {"id": str(uid), "e": f"wstats-extra-{uid.hex[:8]}@example.com"},
            )
            await s.execute(
                text(
                    "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                    "VALUES (:t, :u, 'editor')"
                ),
                {"t": str(tid), "u": str(uid)},
            )
        await s.commit()

    after = await _get_stats(http_client, make_jwt, owner_id, tid)
    assert after["members"] == base + n


async def test_pending_invites_count_increases_by_seeded(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Adding N pending invites raises ``pending_invites`` by N; accepted /
    revoked / expired invites are excluded."""
    tid, owner_id, _member = await _provision_owner_workspace()
    before = await _get_stats(http_client, make_jwt, owner_id, tid)
    base = before["pending_invites"]
    assert isinstance(base, int)

    n = 2
    expires = datetime.now(UTC) + timedelta(days=7)
    async with SessionLocal() as s:
        for _ in range(n):
            await s.execute(
                text(
                    "INSERT INTO tenant_invites (tenant_id, email, role, invited_by, expires_at) "
                    "VALUES (:t, :e, 'editor', :inv, :exp)"
                ),
                {
                    "t": str(tid),
                    "e": f"wstats-invite-{uuid4().hex[:8]}@example.com",
                    "inv": str(owner_id),
                    "exp": expires,
                },
            )
        # One expired invite must NOT be counted.
        await s.execute(
            text(
                "INSERT INTO tenant_invites (tenant_id, email, role, invited_by, expires_at) "
                "VALUES (:t, :e, 'editor', :inv, :exp)"
            ),
            {
                "t": str(tid),
                "e": f"wstats-expired-{uuid4().hex[:8]}@example.com",
                "inv": str(owner_id),
                "exp": datetime.now(UTC) - timedelta(days=1),
            },
        )
        await s.commit()

    after = await _get_stats(http_client, make_jwt, owner_id, tid)
    assert after["pending_invites"] == base + n


async def test_recent_activity_count_increases_by_seeded(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Seeding N workspace-scope audit events for THIS workspace raises
    ``recent_activity`` by N."""
    tid, owner_id, _member = await _provision_owner_workspace()
    before = await _get_stats(http_client, make_jwt, owner_id, tid)
    base = before["recent_activity"]
    assert isinstance(base, int)

    n = 2
    async with SessionLocal() as s:
        for i in range(n):
            await write_audit_event(
                s,
                actor_id=owner_id,
                action=f"test_wstats_activity.{i}",
                target_type="role",
                target_id=uuid4(),
                scope="workspace",
                workspace_id=tid,
            )
        await s.commit()

    after = await _get_stats(http_client, make_jwt, owner_id, tid)
    assert after["recent_activity"] == base + n
