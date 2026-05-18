"""POST /api/signup and GET /api/signup-status."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db
from ..schemas.signup import SignupRequest, SignupResponse, SignupStatus
from ..services.platform_settings import is_signups_enabled
from ..services.signup import (
    EmailProviderUnavailableError,
    EmailTakenError,
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
async def signup(
    body: SignupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SignupResponse:
    try:
        await create_signup_user(db=db, email=body.email, password=body.password)
    except SignupsDisabledError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "signups_disabled") from e
    except EmailTakenError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "email_taken") from e
    except EmailProviderUnavailableError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return SignupResponse(state="confirm_email_sent")
