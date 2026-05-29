"""POST /api/invites/accept — generic acceptance for both kinds.

PAR-A C2: invite ids are read from ``identity.app_metadata`` (service-role
only writable). PAR-A H8: rate-limited at 10 req/IP/hour.

Note on imports: this module deliberately does NOT use
``from __future__ import annotations``. SlowAPI wraps the route via
``functools.wraps``; FastAPI then resolves forward-referenced annotations
using the OUTER wrapper's ``__globals__`` (slowapi.extension), which doesn't
see this module's imports. Using runtime (non-deferred) annotations keeps
``AuthIdentity`` as a concrete type at decoration time.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..core.rate_limit import INVITE_ACCEPT_RATE, limiter
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
@limiter.limit(INVITE_ACCEPT_RATE)
async def accept(
    request: Request,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AcceptInviteResult:
    # PAR-D M1: caller-owns-transaction — commit on success, roll back on any
    # typed error so the request never leaves an open/half-applied tx.
    try:
        result = await accept_invite(
            db,
            user_id=identity.user_id,
            email=identity.email,
            app_metadata=identity.app_metadata,
        )
        await db.commit()
    except NoInviteError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no_invite") from e
    except InviteRevokedError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invite_revoked") from e
    except InviteExpiredError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invite_expired") from e
    except InviteAlreadyAcceptedError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_already_accepted") from e
    except AlreadyProvisionedError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "already_provisioned") from e
    except EmailMismatchError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "email_mismatch") from e
    return AcceptInviteResult.model_validate(result)
