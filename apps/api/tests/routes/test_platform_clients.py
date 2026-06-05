"""Tests for ``GET /api/platform/clients/{slug}`` — platform-scope client detail.

The endpoint lets a platform operator who holds ``platform.clients.read`` (a
PLATFORM-scope perm, no workspace_id) read ANY client tenant's info + members —
INCLUDING a tenant they are NOT a member of (the intended cross-tenant
capability). A caller lacking the perm gets 403; an unknown slug gets a
sanitized 404.

Test-data hygiene: managed DB, ``@example.com`` emails, no super_admin created
here, crash-proof teardown via try/finally that DELETEs in FK-safe order.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser
from xtrusio_api.rbac.grants import grant_role
from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _insert_auth_user(s: object, uid: UUID, email: str) -> None:
    await s.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) "
            "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
            "'authenticated',:e,'',now(),now(),now())"
        ),
        {"id": str(uid), "e": email},
    )


@pytest_asyncio.fixture
async def platform_admin_user() -> AsyncIterator[PlatformUser]:
    """Platform user holding the resolver-visible ``admin`` grant — under the
    P3b matrix ``admin`` holds ``platform.clients.read``."""
    user_id = uuid4()
    email = f"pc-padm-{user_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await _insert_auth_user(s, user_id, email)
        pu = PlatformUser(id=user_id, email=email, role=PlatformRole.ADMIN, is_active=True)
        s.add(pu)
        await grant_role(s, auth_user_id=user_id, scope="platform", key="admin")
        await s.commit()
        await s.refresh(pu)
    try:
        yield pu
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM user_roles WHERE auth_user_id = :id"), {"id": str(user_id)}
            )
            await s.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
            await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await s.commit()


@pytest_asyncio.fixture
async def unprivileged_user() -> AsyncIterator[PlatformUser]:
    """Platform user with NO platform grant — holds no platform permission."""
    user_id = uuid4()
    email = f"pc-noperm-{user_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await _insert_auth_user(s, user_id, email)
        pu = PlatformUser(id=user_id, email=email, role=PlatformRole.EDITOR, is_active=True)
        s.add(pu)
        await s.commit()
        await s.refresh(pu)
    try:
        yield pu
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM user_roles WHERE auth_user_id = :id"), {"id": str(user_id)}
            )
            await s.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
            await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await s.commit()


@pytest_asyncio.fixture
async def seeded_client() -> AsyncIterator[dict[str, object]]:
    """A client tenant with an owner + an editor member. Neither member is the
    caller in the cross-tenant test — that's the point: the platform operator is
    NOT a member of this tenant.
    """
    tid, owner_id, editor_id = uuid4(), uuid4(), uuid4()
    slug = f"pc-client-{tid.hex[:8]}"
    owner_email = f"pc-owner-{owner_id.hex[:8]}@example.com"
    editor_email = f"pc-editor-{editor_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        for uid, email in ((owner_id, owner_email), (editor_id, editor_email)):
            await _insert_auth_user(s, uid, email)
            await s.execute(
                text(
                    "INSERT INTO platform_users (id, email, role, is_active) "
                    "VALUES (:id, :e, 'editor', true)"
                ),
                {"id": str(uid), "e": email},
            )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": slug, "n": "PC Client Co", "u": str(owner_id)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :o, 'owner'), (:t, :e, 'editor')"
            ),
            {"t": str(tid), "o": str(owner_id), "e": str(editor_id)},
        )
        await s.commit()
    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    try:
        yield {
            "tenant_id": tid,
            "slug": slug,
            "owner_id": owner_id,
            "owner_email": owner_email,
            "editor_id": editor_id,
            "editor_email": editor_email,
        }
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM tenant_memberships WHERE tenant_id = :t"), {"t": str(tid)}
            )
            await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tid)})
            for uid in (owner_id, editor_id):
                await s.execute(
                    text("DELETE FROM user_roles WHERE auth_user_id = :id"), {"id": str(uid)}
                )
                await s.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(uid)})
                await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(uid)})
            await s.commit()


async def test_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/platform/clients/anything")
    assert res.status_code == 401


async def test_403_for_caller_without_platform_clients_read(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    unprivileged_user: PlatformUser,
    seeded_client: dict[str, object],
) -> None:
    token = make_jwt(sub=unprivileged_user.id)
    res = await http_client.get(
        f"/api/platform/clients/{seeded_client['slug']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_404_for_unknown_slug(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    platform_admin_user: PlatformUser,
) -> None:
    token = make_jwt(sub=platform_admin_user.id)
    res = await http_client.get(
        f"/api/platform/clients/pc-nope-{uuid4().hex[:8]}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404
    # Sanitized: a fixed detail, no slug echo.
    assert res.json()["detail"] == "client not found"


async def test_platform_admin_reads_any_tenant_incl_non_member(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    platform_admin_user: PlatformUser,
    seeded_client: dict[str, object],
) -> None:
    """The platform admin is NOT a member of ``seeded_client`` yet reads its
    info + both members — the intended cross-tenant capability."""
    token = make_jwt(sub=platform_admin_user.id)
    res = await http_client.get(
        f"/api/platform/clients/{seeded_client['slug']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["slug"] == seeded_client["slug"]
    assert body["name"] == "PC Client Co"
    assert body["id"] == str(seeded_client["tenant_id"])
    assert body["member_count"] == 2
    assert body["owner_email"] == seeded_client["owner_email"]
    by_uid = {m["auth_user_id"]: m for m in body["members"]}
    assert set(by_uid) == {
        str(seeded_client["owner_id"]),
        str(seeded_client["editor_id"]),
    }
    assert by_uid[str(seeded_client["owner_id"])]["role"] == "owner"
    assert by_uid[str(seeded_client["editor_id"])]["role"] == "editor"
    assert by_uid[str(seeded_client["owner_id"])]["email"] == seeded_client["owner_email"]
    assert all(m["email"].endswith("@example.com") for m in body["members"])
