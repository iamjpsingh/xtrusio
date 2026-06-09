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

``rbac_audit_log.actor_auth_user_id`` is an FK to ``auth.users``; a GoTrue
``actor_id`` does not always resolve to a live row (a ``user_deleted`` event, an
external/anonymous actor). We write inside a SAVEPOINT and, on the FK violation,
re-record with a NULL FK actor (the original id stays in ``after``) — so an
unresolvable actor never 500s (which would make Supabase retry forever).

Retry posture: a webhook caller that retries does so on a non-2xx response, so
we return 200 for EVERY well-formed delivery we simply can't turn into an event
(wrong table / non-INSERT / missing record / missing-or-blank action) — those
are logged, never retried. Non-2xx is reserved for things a retry can't fix
anyway: 401 for a bad/absent secret (operator misconfig), and FastAPI's own 422
for a structurally malformed body. This keeps a schema-evolution edge case (a
future GoTrue payload shape we don't recognise) from becoming an infinite retry
loop. There is no cross-delivery dedup (Database Webhooks fire once per INSERT;
a duplicate auth row in the feed is rare and low-severity) — ``after.gotrue_event_id``
is captured so a future dedup/migration is possible.
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import write_audit_event
from ..core.config import get_settings
from ..core.db import get_db
from ..core.logging import get_logger

_log = get_logger(__name__)

router = APIRouter(prefix="/api/internal/auth-events", tags=["internal-auth-events"])

_AUDIT_TABLE = "audit_log_entries"

# GoTrue actions we deliberately DROP rather than record — pure background noise
# that would drown the activity feed. ``token_refreshed`` fires on every silent
# session refresh (~hourly per active user), so a handful of active users would
# bury every meaningful auth event (login/logout/recovery) under refresh rows.
_NOISE_ACTIONS = frozenset({"token_refreshed"})


class _AuthRecord(BaseModel):
    # The auth.audit_log_entries row Supabase sends as the webhook ``record``.
    # We read the GoTrue ``payload`` (action/actor) plus the row's own
    # id/created_at/ip for traceability; unknown columns are ignored.
    id: str | None = None
    payload: dict[str, Any] = {}
    ip_address: str | None = None
    created_at: str | None = None


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


# NOTE: this route is exempted from the SlowAPI authenticated catch-all in
# ``main.py`` (``limiter.exempt(ingest_auth_event)``) rather than via the
# ``@limiter.exempt`` decorator — slowapi's decorator is untyped (trips
# ``--strict``) and, more importantly, the catch-all is IP-keyed for tokenless
# callers; Supabase's webhook arrives from a single egress IP, so on a busy
# project the 60/min bucket would throttle legitimate auth events.
@router.post("", status_code=status.HTTP_200_OK)
async def ingest_auth_event(
    body: _WebhookBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    expected = get_settings().auth_webhook_secret
    # Always run compare_digest (even when the header is absent) so a missing
    # header and a wrong secret take the same path — no presence timing signal.
    if not secrets.compare_digest(x_webhook_secret or "", expected):
        # Opaque — do not reveal whether the header was missing vs wrong.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")

    # Ignore (200, no retry) anything that isn't an INSERT on audit_log_entries.
    if body.type != "INSERT" or body.table != _AUDIT_TABLE or body.record is None:
        return {"status": "ignored"}

    payload = body.record.payload
    gotrue_action = payload.get("action")
    if not isinstance(gotrue_action, str) or not gotrue_action:
        # A well-formed INSERT whose payload we can't turn into an event (no
        # action). Treat it like the other ignore cases — log + 200, never a
        # retry-triggering non-2xx — so a GoTrue schema change can't retry-loop.
        _log.warning("auth_event_missing_action")
        return {"status": "ignored"}

    # Drop background-noise actions (e.g. token_refreshed) — 200, not written.
    if gotrue_action in _NOISE_ACTIONS:
        return {"status": "ignored"}

    actor_id = _coerce_uuid(payload.get("actor_id"))
    after: dict[str, Any] = {"action": gotrue_action}
    actor_username = payload.get("actor_username")
    if isinstance(actor_username, str) and actor_username:
        after["actor_username"] = actor_username
    # Keep the GoTrue actor id in the payload even if the FK column below ends up
    # NULL (unresolvable actor) — the actor info is then never lost.
    if actor_id is not None:
        after["actor_id"] = str(actor_id)
    if body.record.ip_address:
        after["ip_address"] = body.record.ip_address
    if body.record.id:
        after["gotrue_event_id"] = body.record.id
    if body.record.created_at:
        after["gotrue_created_at"] = body.record.created_at

    # target is the acting user when known, else the action itself (the column
    # is text, so a non-uuid sentinel is fine).
    target_id: UUID | str = actor_id if actor_id is not None else gotrue_action
    fk_actor: UUID | None = actor_id
    try:
        # SAVEPOINT: the actor_id -> auth.users FK may not resolve (see module
        # docstring). A raw FK violation would 500 → Supabase retries forever.
        async with db.begin_nested():
            await write_audit_event(
                db,
                actor_id=fk_actor,
                action=f"auth.{gotrue_action}",
                target_type="auth_user",
                target_id=target_id,
                scope="platform",
                after=after,
            )
    except IntegrityError:
        # Re-record with a NULL FK actor; the GoTrue id stays in ``after``.
        fk_actor = None
        await write_audit_event(
            db,
            actor_id=None,
            action=f"auth.{gotrue_action}",
            target_type="auth_user",
            target_id=target_id,
            scope="platform",
            after=after,
        )
    await db.commit()
    _log.info("auth_event_ingested", action=gotrue_action, actor_resolved=fk_actor is not None)
    return {"status": "ok"}
