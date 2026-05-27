"""POST /api/signup and GET /api/signup-status.

PAR-A H8 (non-enumeration): /signup ALWAYS returns 202 ``confirm_email_sent``
when signups are enabled — there is no 409 ``email_taken`` branch. If the
email is already registered, the service silently sends a password-reset
email to the existing account-holder (same UX surface; no oracle for an
attacker to enumerate registered emails).

PAR-A H8 (rate limit): the limiter is applied at 5 req/IP/hour (legit signup
is a one-shot operation; brute force requires orders of magnitude more).

Note: ``from __future__ import annotations`` is intentionally OMITTED here —
SlowAPI wraps the route via ``functools.wraps``; FastAPI then resolves
forward-referenced annotations using the OUTER wrapper's ``__globals__``
(slowapi.extension), which doesn't see this module's imports.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db
from ..core.rate_limit import SIGNUP_RATE, limiter
from ..schemas.signup import SignupRequest, SignupResponse, SignupStatus
from ..services.platform_settings import is_signups_enabled
from ..services.signup import (
    EmailProviderUnavailableError,
    SignupsDisabledError,
    create_signup_user,
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
    try:
        await create_signup_user(db=db, email=body.email, password=body.password)
    except SignupsDisabledError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "signups_disabled") from e
    except EmailProviderUnavailableError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return SignupResponse(state="confirm_email_sent")
