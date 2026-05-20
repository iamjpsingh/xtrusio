"""Service-level tests for the signup orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from gotrue.errors import AuthApiError
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.services.signup import EmailTakenError, create_signup_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(autouse=True)
def _patch_signups_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass the platform_settings gate so we exercise the create_user path."""

    async def _yes(_db: AsyncSession) -> bool:
        return True

    monkeypatch.setattr("xtrusio_api.services.signup.is_signups_enabled", _yes)


async def test_create_signup_user_maps_authapierror_to_emailtaken(
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    mock_supabase_admin.auth.admin.create_user.side_effect = AuthApiError(
        "email already registered", 422, "email_exists"
    )
    with pytest.raises(EmailTakenError):
        await create_signup_user(
            db=db_session, email="dup@example.com", password="hunter22hunter22"
        )


async def test_create_signup_user_passes_unknown_authapierror_through(
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    mock_supabase_admin.auth.admin.create_user.side_effect = AuthApiError(
        "weak password", 400, "weak_password"
    )
    with pytest.raises(AuthApiError):
        await create_signup_user(
            db=db_session, email="weak@example.com", password="hunter22hunter22"
        )
