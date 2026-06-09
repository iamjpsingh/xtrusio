"""POST /api/signup and GET /api/signup-status.

Flow B (existence-revealing — an INTENTIONAL reversal of the old
non-enumeration design; the product owner chose clarity): /signup answers
``202 confirm_email_sent`` for a NEW email (account created, verification
email sent) and ``409 email_exists`` for an already-registered email
(verified OR unverified, not distinguished; no account created, no email of
any kind sent). Disabled → ``403 signups_disabled``.

Rate limit: the slowapi limiter is applied at 5 req/IP/hour (legit signup is a
one-shot operation; brute force requires orders of magnitude more).

RL-2 (per-email throttle): in addition to the per-IP limit, BOTH endpoints are
throttled per NORMALIZED TARGET EMAIL via Valkey (``core.email_throttle``).
This caps email-bombing — an attacker rotating source IPs could otherwise
flood a known victim's inbox while dodging the per-IP bucket. The two limits
are defense-in-depth (per-IP AND per-email). The over-limit ``429`` is raised
BEFORE any account-state lookup, purely on request count.

Note: ``from __future__ import annotations`` is intentionally OMITTED here —
SlowAPI wraps the route via ``functools.wraps``; FastAPI then resolves
forward-referenced annotations using the OUTER wrapper's ``__globals__``
(slowapi.extension), which doesn't see this module's imports.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db
from ..core.email_throttle import is_email_throttled
from ..core.rate_limit import SIGNUP_RATE, limiter
from ..schemas.signup import (
    SignupRequest,
    SignupResendRequest,
    SignupResponse,
    SignupStatus,
)
from ..services.platform_settings import is_signups_enabled
from ..services.signup import (
    EmailAlreadyExistsError,
    EmailProviderUnavailableError,
    SignupsDisabledError,
    create_signup_user,
    resend_signup_confirmation,
)

router = APIRouter(prefix="/api", tags=["signup"])


@router.get("/signup-status", response_model=SignupStatus)
async def signup_status(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SignupStatus:
    return SignupStatus(signups_enabled=await is_signups_enabled(db))


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(SIGNUP_RATE)
async def signup(
    request: Request,
    body: SignupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SignupResponse:
    # RL-2: per-email throttle. Checked BEFORE any account-state lookup or
    # Supabase call so the 429 is purely request-count based.
    if await is_email_throttled(body.email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")
    try:
        await create_signup_user(db=db, email=body.email, password=body.password)
    except SignupsDisabledError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "signups_disabled") from e
    except EmailAlreadyExistsError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "email_exists") from e
    except EmailProviderUnavailableError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return SignupResponse(state="confirm_email_sent")


@router.post("/signup/resend", response_model=SignupResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(SIGNUP_RATE)
async def signup_resend(
    request: Request,
    body: SignupResendRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SignupResponse:
    """Resend the signup-confirmation email.

    Gated behind ``signups_enabled`` and rate-limited identically to /signup
    (5/IP/hr per-IP PLUS the RL-2 per-email throttle). Returns 202
    ``confirm_email_sent`` when enabled; an ineligible address (already
    confirmed, etc.) is swallowed to the same 202 by the service layer.
    """
    # RL-2: per-email throttle — same uniform, account-state-blind 429 as
    # /signup. Resend is the more obvious email-bomb vector (no password
    # needed), so it must share the per-email ceiling.
    if await is_email_throttled(body.email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")
    try:
        await resend_signup_confirmation(db=db, email=body.email)
    except SignupsDisabledError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "signups_disabled") from e
    except EmailProviderUnavailableError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return SignupResponse(state="confirm_email_sent")
