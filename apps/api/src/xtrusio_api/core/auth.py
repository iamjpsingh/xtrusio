"""JWT validation + auth dependencies (RS256 via JWKS)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.platform_user import PlatformRole, PlatformUser
from .config import get_settings
from .db import get_db

_AUDIENCE = "authenticated"
_JWKS_CACHE: dict[str, tuple[dict[str, Any], float]] = {}
_ALLOWED_ALGS: frozenset[str] = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384"})


@dataclass
class CurrentUser:
    user_id: UUID
    email: str
    role: PlatformRole
    is_active: bool


async def _fetch_jwks(url: str) -> dict[str, Any]:
    """Fetch JWKS doc with an in-process TTL cache. Network bound, async."""
    cached = _JWKS_CACHE.get(url)
    if cached and cached[1] > time.time():
        return cached[0]
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.jwks_fetch_timeout_sec) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        jwks: dict[str, Any] = resp.json()
    _JWKS_CACHE[url] = (jwks, time.time() + settings.jwks_ttl_sec)
    return jwks


async def _decode_jwt(token: str) -> dict[str, Any]:
    """Decode + verify a Supabase JWT using the project's JWKS."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token header: {e}") from e
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
    alg = key.get("alg", "RS256")
    if alg not in _ALLOWED_ALGS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unsupported alg")
    try:
        payload: dict[str, Any] = jwt.decode(token, key, algorithms=[alg], audience=_AUDIENCE)
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e
    return payload


async def get_current_user(
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
    return CurrentUser(user_id=row.id, email=row.email, role=row.role, is_active=row.is_active)


@dataclass
class AuthIdentity:
    user_id: UUID
    email: str
    user_metadata: dict[str, Any]


async def require_authenticated(
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
    return AuthIdentity(user_id=user_id, email=row[0], user_metadata=user_metadata)
