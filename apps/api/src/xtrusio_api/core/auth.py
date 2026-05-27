"""JWT validation + auth dependencies (RS256 via JWKS).

PAR-A C1: algorithms pinned to RS256 (no ES256/RS384/RS512); ``alg`` validated
from the JWT header BEFORE the JWKS lookup; ``iss``/``aud``/``exp``/``iat``/``sub``
are required claims; ``iss`` is pinned to ``f"{supabase_url}/auth/v1"``;
``aud`` is pinned to ``"authenticated"`` (the Supabase default).

PAR-A C2: ``app_metadata`` is surfaced on :class:`AuthIdentity` (service-role
writable only — the invitee cannot forge it). Invite acceptance reads invite
ids from ``app_metadata``, never ``user_metadata``.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.platform_user import PlatformRole, PlatformUser
from .config import get_settings
from .db import get_db

_AUDIENCE = "authenticated"
_REQUIRED_CLAIMS = ("exp", "iat", "aud", "iss", "sub")
# python-jose uses ``require_<claim>: True`` keys rather than a ``require`` list;
# translate once at import time so ``_decode_jwt`` can pass it verbatim.
_JWT_OPTIONS: dict[str, Any] = {f"require_{c}": True for c in _REQUIRED_CLAIMS}
_JWKS_CACHE: dict[str, tuple[dict[str, Any], float]] = {}
_JWKS_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _issuer() -> str:
    """Canonical Supabase issuer for the configured project."""
    return f"{get_settings().supabase_url.rstrip('/')}/auth/v1"


@dataclass
class CurrentUser:
    user_id: UUID
    email: str
    role: PlatformRole
    is_active: bool


async def _fetch_jwks_uncached(url: str) -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.jwks_fetch_timeout_sec) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        out: dict[str, Any] = resp.json()
        return out


async def _fetch_jwks(url: str) -> dict[str, Any]:
    """Fetch JWKS doc with an in-process TTL cache and per-URL coalescing.

    Why the lock: under cold-start with N concurrent callers, the unlocked
    version fired N httpx fetches. The lock collapses that to 1; later callers
    observe the cached value when they acquire the lock and skip the network.
    """
    cached = _JWKS_CACHE.get(url)
    if cached and cached[1] > time.time():
        return cached[0]
    async with _JWKS_LOCKS[url]:
        cached = _JWKS_CACHE.get(url)
        if cached and cached[1] > time.time():
            return cached[0]
        jwks = await _fetch_jwks_uncached(url)
        _JWKS_CACHE[url] = (jwks, time.time() + get_settings().jwks_ttl_sec)
        return jwks


async def _decode_jwt(token: str) -> dict[str, Any]:
    """Decode + verify a Supabase JWT using the project's JWKS.

    Hardened (PAR-A C1):
      - ``alg`` validated against the *header* before the JWKS lookup —
        an attacker who controls the header can no longer suggest a weaker
        algorithm; only RS256 is accepted.
      - Required claims enforced via the JWT lib's ``options["require"]``
        list (exp, iat, aud, iss, sub).
      - Issuer pinned to ``<supabase_url>/auth/v1``.
      - Audience pinned to ``"authenticated"``.
      - All claim mismatches surface as 401.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token header: {e}") from e
    if header.get("alg") != "RS256":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unsupported alg")
    kid = header.get("kid")
    if not kid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing kid")
    try:
        jwks = await _fetch_jwks(get_settings().supabase_jwks_url)
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"jwks fetch failed: {e}") from e
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no matching jwks key")
    # Also defensively check the key alg metadata — RS256 only.
    key_alg = key.get("alg")
    if key_alg is not None and key_alg != "RS256":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unsupported alg")
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=_AUDIENCE,
            issuer=_issuer(),
            options=_JWT_OPTIONS,
        )
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e
    return payload


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = await _decode_jwt(token)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")
    try:
        user_id = UUID(sub)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid sub") from e

    row = (
        await db.execute(select(PlatformUser).where(PlatformUser.id == user_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not provisioned")
    if not row.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user disabled")
    # Publish identity on request.state so the rate-limiter key_func can read
    # it (PAR-A H8). AuthIdentity carries the same user_id; this is a
    # lightweight shim so user-keyed limits work on routes that already use
    # ``CurrentUser`` instead of ``AuthIdentity``.
    request.state.identity = AuthIdentity(
        user_id=row.id,
        email=row.email,
        user_metadata=payload.get("user_metadata") or {},
        app_metadata=payload.get("app_metadata") or {},
    )
    return CurrentUser(user_id=row.id, email=row.email, role=row.role, is_active=row.is_active)


@dataclass
class AuthIdentity:
    user_id: UUID
    email: str
    user_metadata: dict[str, Any]
    # PAR-A C2: surface ``app_metadata`` (service-role-only writable) so invite
    # acceptance can read invite ids from a non-forgeable claim.
    app_metadata: dict[str, Any] = field(default_factory=dict)


async def require_authenticated(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthIdentity:
    """JWT-validated identity. Does NOT require a platform_users row.

    Used for endpoints that fresh signup users (no platform_users, no
    tenant_memberships yet) need to call — currently /onboarding/tenants and
    /me. The JWT goes through the same JWKS verification path; only the
    post-decode platform_users lookup is skipped.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = await _decode_jwt(token)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")
    try:
        user_id = UUID(sub)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid sub") from e
    from sqlalchemy import text  # local import to avoid top-level churn

    row = (
        await db.execute(text("SELECT email FROM auth.users WHERE id = :id"), {"id": str(user_id)})
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not in auth.users")
    user_metadata = payload.get("user_metadata") or {}
    app_metadata = payload.get("app_metadata") or {}
    identity = AuthIdentity(
        user_id=user_id,
        email=row[0],
        user_metadata=user_metadata,
        app_metadata=app_metadata,
    )
    # Publish identity on request.state so the rate-limiter key_func can read
    # it (PAR-A H8 — user-keyed limits).
    request.state.identity = identity
    return identity
