"""POST /api/internal/auth-events — Supabase Database-Webhook ingest for GoTrue
auth events (login/logout/etc) into the unified activity feed's ``auth`` category.

A Supabase Database Webhook on INSERT of ``auth.audit_log_entries`` POSTs each
new GoTrue audit row here. This endpoint is UNAUTHENTICATED in the JWT sense
(Supabase calls it, not a browser/user) — its only gate is a shared secret the
webhook sends in the ``X-Webhook-Secret`` header, compared in constant time
against ``AUTH_WEBHOOK_SECRET``. (Supabase Database Webhooks support custom
headers; full body HMAC signing is not a built-in for them, so a shared-secret
header is the supported mechanism.)

Each accepted event is written as one ``rbac_audit_log`` row with
``action='auth.<gotrue_action>'``, ``scope='platform'``, ``category`` resolved
to ``auth`` via the catalog. The actor is the GoTrue ``actor_id`` (nullable —
e.g. an anonymous failed login has no actor).

Idempotency/retries: Supabase retries on non-2xx, so we return 200 for events
we deliberately ignore (wrong table / non-INSERT) to avoid pointless retries,
401 only for a bad secret, and 400 only for a structurally invalid body.
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import write_audit_event
from ..core.config import get_settings
from ..core.db import get_db
from ..core.logging import get_logger
from ..core.rate_limit import limiter

_log = get_logger(__name__)

router = APIRouter(prefix="/api/internal/auth-events", tags=["internal-auth-events"])

_AUDIT_TABLE = "audit_log_entries"


class _AuthRecord(BaseModel):
    payload: dict[str, Any] = {}
    ip_address: str | None = None


class _WebhookBody(BaseModel):
    type: str
    table: str
    record: _AuthRecord | None = None


def _coerce_uuid(value: Any) -> UUID | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


@router.post("", status_code=status.HTTP_200_OK)
@limiter.exempt
async def ingest_auth_event(
    body: _WebhookBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    expected = get_settings().auth_webhook_secret
    if not x_webhook_secret or not secrets.compare_digest(x_webhook_secret, expected):
        # Opaque — do not reveal whether the header was missing vs wrong.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")

    # Ignore (200, no retry) anything that isn't an INSERT on audit_log_entries.
    if body.type != "INSERT" or body.table != _AUDIT_TABLE or body.record is None:
        return {"status": "ignored"}

    payload = body.record.payload
    gotrue_action = payload.get("action")
    if not isinstance(gotrue_action, str) or not gotrue_action:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing action")

    actor_id = _coerce_uuid(payload.get("actor_id"))
    after: dict[str, Any] = {"action": gotrue_action}
    actor_username = payload.get("actor_username")
    if isinstance(actor_username, str) and actor_username:
        after["actor_username"] = actor_username
    if body.record.ip_address:
        after["ip_address"] = body.record.ip_address

    await write_audit_event(
        db,
        actor_id=actor_id,
        action=f"auth.{gotrue_action}",
        target_type="auth_user",
        # target is the acting user when known, else the action itself (the
        # column is text, so a non-uuid sentinel is fine).
        target_id=actor_id if actor_id is not None else gotrue_action,
        scope="platform",
        after=after,
    )
    await db.commit()
    _log.info("auth_event_ingested", action=gotrue_action, has_actor=actor_id is not None)
    return {"status": "ok"}
