"""Tests for POST /api/internal/auth-events (GoTrue auth-event webhook ingest).

The endpoint is UNAUTHENTICATED in the JWT sense — Supabase's Database Webhook
calls it, not a browser. Its only gate is the shared ``AUTH_WEBHOOK_SECRET``
presented in the ``X-Webhook-Secret`` header (constant-time compared). Each
accepted INSERT on ``auth.audit_log_entries`` becomes one ``rbac_audit_log`` row
in the activity feed's ``auth`` category.

Cleanup is keyed on the unique actor_id (real-actor cases) or the unique GoTrue
action we synthesise (anonymous / unresolvable-actor cases), so these tests
never touch real audit rows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.config import get_settings
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")

_SECRET = get_settings().auth_webhook_secret
_HDR = {"X-Webhook-Secret": _SECRET}


def _insert_body(
    *,
    action: str | None,
    actor_id: UUID | None = None,
    actor_username: str | None = "actor@example.com",
    ip_address: str | None = "203.0.113.7",
    event_id: UUID | None = None,
) -> dict[str, Any]:
    """Build a Supabase Database-Webhook INSERT body for auth.audit_log_entries."""
    payload: dict[str, Any] = {}
    if action is not None:
        payload["action"] = action
    if actor_id is not None:
        payload["actor_id"] = str(actor_id)
    if actor_username is not None:
        payload["actor_username"] = actor_username
    record: dict[str, Any] = {"payload": payload}
    if ip_address is not None:
        record["ip_address"] = ip_address
    if event_id is not None:
        record["id"] = str(event_id)
    return {"type": "INSERT", "table": "audit_log_entries", "record": record}


async def _row_for_actor(actor_id: UUID) -> dict[str, Any] | None:
    async with SessionLocal() as s:
        m = (
            (
                await s.execute(
                    text(
                        "SELECT action, scope, target_type, actor_auth_user_id, after "
                        "FROM rbac_audit_log WHERE actor_auth_user_id = :id "
                        "ORDER BY id DESC LIMIT 1"
                    ),
                    {"id": str(actor_id)},
                )
            )
            .mappings()
            .first()
        )
    return dict(m) if m is not None else None


async def _row_for_action(action: str) -> dict[str, Any] | None:
    async with SessionLocal() as s:
        m = (
            (
                await s.execute(
                    text(
                        "SELECT action, scope, target_type, actor_auth_user_id, target_id, after "
                        "FROM rbac_audit_log WHERE action = :a ORDER BY id DESC LIMIT 1"
                    ),
                    {"a": action},
                )
            )
            .mappings()
            .first()
        )
    return dict(m) if m is not None else None


async def _cleanup_action(action: str) -> None:
    async with SessionLocal() as s:
        await s.execute(text("DELETE FROM rbac_audit_log WHERE action = :a"), {"a": action})
        await s.commit()


@pytest_asyncio.fixture
async def auth_user() -> AsyncIterator[UUID]:
    """A real auth.users row so the actor_id FK resolves, plus teardown that
    removes its audit rows BEFORE the user (FK is ON DELETE SET NULL, so deleting
    the user would orphan-null the rows instead of removing them)."""
    uid = uuid4()
    email = f"authevt-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(uid), "email": email},
        )
        await s.commit()
    try:
        yield uid
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :id"), {"id": str(uid)}
            )
            await s.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(uid)})
            await s.commit()


# --- secret gate -----------------------------------------------------------


async def test_missing_secret_returns_401(http_client: AsyncClient) -> None:
    res = await http_client.post("/api/internal/auth-events", json=_insert_body(action="login"))
    assert res.status_code == 401
    assert res.json()["detail"] == "unauthorized"


async def test_wrong_secret_returns_401(http_client: AsyncClient) -> None:
    res = await http_client.post(
        "/api/internal/auth-events",
        headers={"X-Webhook-Secret": "definitely-not-the-secret"},
        json=_insert_body(action="login"),
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "unauthorized"


# --- ignore semantics (200, no Supabase retry) -----------------------------


async def test_non_insert_event_is_ignored(http_client: AsyncClient) -> None:
    body = _insert_body(action="login")
    body["type"] = "UPDATE"
    res = await http_client.post("/api/internal/auth-events", headers=_HDR, json=body)
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"


async def test_wrong_table_is_ignored(http_client: AsyncClient) -> None:
    body = _insert_body(action="login")
    body["table"] = "users"
    res = await http_client.post("/api/internal/auth-events", headers=_HDR, json=body)
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"


async def test_missing_record_is_ignored(http_client: AsyncClient) -> None:
    res = await http_client.post(
        "/api/internal/auth-events",
        headers=_HDR,
        json={"type": "INSERT", "table": "audit_log_entries"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"


async def test_missing_action_is_ignored(http_client: AsyncClient) -> None:
    # A well-formed INSERT whose payload lacks an action is ignored (200), NOT a
    # 4xx — a non-2xx could make the webhook caller retry the unprocessable event
    # forever if GoTrue's payload shape ever drifts.
    res = await http_client.post(
        "/api/internal/auth-events", headers=_HDR, json=_insert_body(action=None)
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"


async def test_token_refreshed_is_dropped_as_noise(
    http_client: AsyncClient, auth_user: UUID
) -> None:
    # token_refreshed is background noise (fires ~hourly per active session) →
    # ignored (200), never written, so it can't drown the feed.
    res = await http_client.post(
        "/api/internal/auth-events",
        headers=_HDR,
        json=_insert_body(action="token_refreshed", actor_id=auth_user),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"
    assert await _row_for_action("auth.token_refreshed") is None


# --- happy path ------------------------------------------------------------


async def test_happy_path_writes_auth_row(http_client: AsyncClient, auth_user: UUID) -> None:
    event_id = uuid4()
    res = await http_client.post(
        "/api/internal/auth-events",
        headers=_HDR,
        json=_insert_body(
            action="login", actor_id=auth_user, ip_address="203.0.113.9", event_id=event_id
        ),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ok"

    row = await _row_for_actor(auth_user)
    assert row is not None
    assert row["action"] == "auth.login"
    assert row["scope"] == "platform"
    assert row["target_type"] == "auth_user"
    assert str(row["actor_auth_user_id"]) == str(auth_user)
    after = row["after"]
    assert after["action"] == "login"
    assert after["ip_address"] == "203.0.113.9"
    assert after["actor_username"] == "actor@example.com"
    assert after["actor_id"] == str(auth_user)
    assert after["gotrue_event_id"] == str(event_id)


async def test_anonymous_actor_records_null_fk(http_client: AsyncClient) -> None:
    gotrue_action = f"evt_{uuid4().hex}"
    action = f"auth.{gotrue_action}"
    try:
        res = await http_client.post(
            "/api/internal/auth-events",
            headers=_HDR,
            json=_insert_body(
                action=gotrue_action, actor_id=None, actor_username=None, ip_address=None
            ),
        )
        assert res.status_code == 200, res.text
        row = await _row_for_action(action)
        assert row is not None
        assert row["actor_auth_user_id"] is None
        # No actor → the GoTrue action is the (text) target sentinel.
        assert row["target_id"] == gotrue_action
        assert "actor_id" not in row["after"]
    finally:
        await _cleanup_action(action)


async def test_unresolvable_actor_does_not_500_and_keeps_actor_in_payload(
    http_client: AsyncClient,
) -> None:
    """The exact production hazard: a GoTrue actor_id with no auth.users row
    (user_deleted / external actor). Must NOT 500 (Supabase would retry forever)
    — the row is recorded with a NULL FK actor and the id preserved in ``after``."""
    ghost = uuid4()
    gotrue_action = f"evt_{uuid4().hex}"
    action = f"auth.{gotrue_action}"
    try:
        res = await http_client.post(
            "/api/internal/auth-events",
            headers=_HDR,
            json=_insert_body(action=gotrue_action, actor_id=ghost),
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "ok"
        row = await _row_for_action(action)
        assert row is not None
        assert row["actor_auth_user_id"] is None  # FK fell back to NULL
        assert row["after"]["actor_id"] == str(ghost)  # but the id is preserved
        # Target keeps the original actor id (text column, no FK).
        assert row["target_id"] == str(ghost)
    finally:
        await _cleanup_action(action)


# --- end-to-end: visible in the viewer's auth category ---------------------


async def test_ingested_event_appears_in_auth_category(
    http_client: AsyncClient,
    auth_user: UUID,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    res = await http_client.post(
        "/api/internal/auth-events",
        headers=_HDR,
        json=_insert_body(action="logout", actor_id=auth_user),
    )
    assert res.status_code == 200, res.text

    token = make_jwt(sub=existing_super_admin.id)
    page = await http_client.get(
        "/api/platform/audit-log?category=auth&limit=100",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page.status_code == 200, page.text
    mine = [i for i in page.json()["items"] if i["actor_auth_user_id"] == str(auth_user)]
    assert mine, "ingested auth event not visible in the auth category"
    ev = mine[0]
    assert ev["action"] == "auth.logout"
    assert ev["action_label"] == "Signed out"
    assert ev["category"] == "auth"


# --- rate-limit exemption (config-level; the catch-all would otherwise throttle
#     Supabase's single-egress-IP webhook) -----------------------------------


async def test_ingest_route_is_rate_limit_exempt() -> None:
    from xtrusio_api.core.rate_limit import limiter
    from xtrusio_api.routes.internal_auth_events import ingest_auth_event

    name = f"{ingest_auth_event.__module__}.{ingest_auth_event.__name__}"
    assert name in limiter._exempt_routes
