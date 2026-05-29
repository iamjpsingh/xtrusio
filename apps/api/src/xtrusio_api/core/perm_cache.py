"""Valkey-backed cache for effective permission lists (PAR-D M16).

Consumed only by ``GET /me`` (the effective platform-perm list + the per-tenant
perm lists). **The authorization gate — ``require_permission`` →
``has_platform_perm`` / ``has_workspace_perm`` — is never cached**, so a stale
entry can at most make ``/me`` display a slightly out-of-date permission list
for up to ``PERM_CACHE_TTL_SEC`` seconds; it can never grant or deny an actual
request. Invalidation on grant/revoke keeps even the display fresh in the
common case; the short TTL bounds the rest (e.g. role-permission edits).

Every operation is best-effort: a Valkey outage degrades to a cache miss / no-op
(logged at WARN) and the caller falls through to the database, so a Valkey
failure never takes ``/me`` down.

This module is also the consumer that closes M16's "Valkey configured but never
used" finding; the rate limiter (PAR-A) shares the same Valkey instance.
"""

from __future__ import annotations

import json
from uuid import UUID

import redis.asyncio as aioredis

from .config import get_settings
from .logging import get_logger

_log = get_logger(__name__)
_client: aioredis.Redis | None = None


def _get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        # Short timeouts so an unreachable Valkey fails fast into the
        # error-tolerant fallbacks below rather than hanging /me.
        _client = aioredis.from_url(
            get_settings().valkey_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client


async def close_perm_cache() -> None:
    """Close the module Valkey client (FastAPI lifespan shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _key(user_id: UUID, scope: str) -> str:
    """``scope`` is the literal ``'platform'`` or a workspace id string."""
    return f"perm:{user_id}:{scope}"


async def get_platform(user_id: UUID) -> list[str] | None:
    try:
        raw = await _get_client().get(_key(user_id, "platform"))
    except Exception as e:  # Valkey down must not break /me
        _log.warning("perm_cache_get_failed", scope="platform", error=str(e))
        return None
    if raw is None:
        return None
    try:
        loaded: list[str] = json.loads(raw)
        return loaded
    except (ValueError, TypeError):
        return None


async def set_platform(user_id: UUID, perms: list[str]) -> None:
    try:
        await _get_client().set(
            _key(user_id, "platform"),
            json.dumps(perms),
            ex=get_settings().perm_cache_ttl_sec,
        )
    except Exception as e:
        _log.warning("perm_cache_set_failed", scope="platform", error=str(e))


async def get_workspaces(user_id: UUID, workspace_ids: list[UUID]) -> dict[UUID, list[str]]:
    """Return cached perm lists for the hit workspaces only (misses are absent)."""
    if not workspace_ids:
        return {}
    try:
        vals = await _get_client().mget([_key(user_id, str(w)) for w in workspace_ids])
    except Exception as e:
        _log.warning("perm_cache_mget_failed", error=str(e))
        return {}
    out: dict[UUID, list[str]] = {}
    for wid, raw in zip(workspace_ids, vals, strict=True):
        if raw is None:
            continue
        try:
            out[wid] = json.loads(raw)
        except (ValueError, TypeError):
            continue
    return out


async def set_workspaces(user_id: UUID, perms_by_ws: dict[UUID, list[str]]) -> None:
    if not perms_by_ws:
        return
    ttl = get_settings().perm_cache_ttl_sec
    try:
        async with _get_client().pipeline(transaction=False) as pipe:
            for wid, perms in perms_by_ws.items():
                pipe.set(_key(user_id, str(wid)), json.dumps(perms), ex=ttl)
            await pipe.execute()
    except Exception as e:
        _log.warning("perm_cache_mset_failed", error=str(e))


async def clear_all() -> None:
    """Drop every cached perm key. Test helper (per-test isolation) — tolerant
    of a down Valkey so the suite runs whether or not Valkey is up."""
    try:
        client = _get_client()
        keys = [k async for k in client.scan_iter(match="perm:*")]
        if keys:
            await client.delete(*keys)
    except Exception as e:
        _log.warning("perm_cache_clear_failed", error=str(e))


async def invalidate(user_id: UUID, workspace_id: UUID | None) -> None:
    """Drop a user's cached perm list for one scope.

    ``workspace_id is None`` → the platform list (platform grant/revoke);
    otherwise that workspace's list (workspace grant/revoke). Called from the
    grant/revoke services; a delete on a not-yet-committed tx that later rolls
    back is harmless (the next read repopulates from the DB)."""
    scope = "platform" if workspace_id is None else str(workspace_id)
    try:
        await _get_client().delete(_key(user_id, scope))
    except Exception as e:
        _log.warning("perm_cache_invalidate_failed", scope=scope, error=str(e))
