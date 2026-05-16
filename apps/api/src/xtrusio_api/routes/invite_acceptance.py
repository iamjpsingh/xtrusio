"""POST /api/invites/accept — generic acceptance for both kinds."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..schemas.invite import AcceptInviteResult
from ..services.invite_acceptance import (
    AlreadyProvisionedError,
    EmailMismatchError,
    InviteAlreadyAcceptedError,
    InviteExpiredError,
    InviteRevokedError,
    NoInviteError,
    accept_invite,
)

router = APIRouter(prefix="/api/invites", tags=["invite-acceptance"])


@router.post("/accept", response_model=AcceptInviteResult)
async def accept(
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AcceptInviteResult:
    try:
        result = await accept_invite(
            db,
            user_id=identity.user_id,
            email=identity.email,
            user_metadata=identity.user_metadata,
        )
    except NoInviteError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no_invite") from e
    except InviteRevokedError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invite_revoked") from e
    except InviteExpiredError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invite_expired") from e
    except InviteAlreadyAcceptedError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_already_accepted") from e
    except AlreadyProvisionedError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_provisioned") from e
    except EmailMismatchError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "email_mismatch") from e
    return AcceptInviteResult.model_validate(result)
