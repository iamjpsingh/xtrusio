"""Service-level tests for the signup orchestrator (native ``sign_up`` model)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.services.signup import (
    EmailProviderUnavailableError,
    SignupsDisabledError,
    create_signup_user,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _patch_gate(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    async def _val(_db: AsyncSession) -> bool:
        return enabled

    monkeypatch.setattr("xtrusio_api.services.signup.is_signups_enabled", _val)


async def test_create_signup_user_gated_off_raises_and_skips_supabase(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Hard gate: disabled → SignupsDisabledError, NO Supabase call at all."""
    _patch_gate(monkeypatch, enabled=False)
    with pytest.raises(SignupsDisabledError):
        await create_signup_user(
            db=db_session, email="gated-off@example.com", password="hunter22hunter22"
        )
    mock_supabase_admin.auth.sign_up.assert_not_called()
    mock_supabase_admin.auth.admin.create_user.assert_not_called()


async def test_create_signup_user_gated_on_calls_native_sign_up(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Enabled → native ``auth.sign_up`` is invoked; ``admin.create_user`` is NOT."""
    _patch_gate(monkeypatch, enabled=True)
    mock_supabase_admin.auth.sign_up.return_value = MagicMock(
        user=MagicMock(id="00000000-0000-0000-0000-000000000777")
    )
    await create_signup_user(db=db_session, email="native@example.com", password="hunter22hunter22")
    mock_supabase_admin.auth.sign_up.assert_called_once_with(
        {"email": "native@example.com", "password": "hunter22hunter22"}
    )
    mock_supabase_admin.auth.admin.create_user.assert_not_called()


async def test_create_signup_user_transport_failure_maps_to_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """A ``sign_up`` transport error surfaces as EmailProviderUnavailableError (→ 502)."""
    _patch_gate(monkeypatch, enabled=True)
    mock_supabase_admin.auth.sign_up.side_effect = httpx.ConnectError("boom")
    with pytest.raises(EmailProviderUnavailableError):
        await create_signup_user(
            db=db_session, email="down@example.com", password="hunter22hunter22"
        )
