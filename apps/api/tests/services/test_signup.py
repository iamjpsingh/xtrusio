"""Service-level tests for the signup orchestrator (existence-aware branching).

``create_signup_user`` keeps the hard ``signups_enabled`` gate, then branches
on the ``auth.users`` lookup so the *email sent* matches the account state —
new → ``sign_up``, unconfirmed → ``resend``, confirmed → ``reset_password_email``
— while the return value is ALWAYS ``None`` (non-enumeration: identical outcome).

Both gate and lookup are patched (mirroring ``_patch_gate``) so branches are
deterministic without real ``auth.users`` rows.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from gotrue.errors import AuthApiError
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.config import get_settings
from xtrusio_api.services.signup import (
    EmailProviderUnavailableError,
    SignupsDisabledError,
    create_signup_user,
    resend_signup_confirmation,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _patch_gate(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    async def _val(_db: AsyncSession) -> bool:
        return enabled

    monkeypatch.setattr("xtrusio_api.services.signup.is_signups_enabled", _val)


def _patch_lookup(monkeypatch: pytest.MonkeyPatch, *, exists: bool, confirmed: bool) -> None:
    async def _val(_db: AsyncSession, _email: str) -> tuple[bool, bool]:
        return (exists, confirmed)

    monkeypatch.setattr("xtrusio_api.services.signup.lookup_auth_user", _val)


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
    mock_supabase_admin.auth.resend.assert_not_called()
    mock_supabase_admin.auth.reset_password_email.assert_not_called()
    mock_supabase_admin.auth.admin.create_user.assert_not_called()


async def test_new_email_calls_sign_up_with_redirect_and_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """New email (no auth.users row) → native ``auth.sign_up`` (keeps the
    ``email_redirect_to`` option) and ``create_signup_user`` returns ``None``."""
    _patch_gate(monkeypatch, enabled=True)
    _patch_lookup(monkeypatch, exists=False, confirmed=False)
    mock_supabase_admin.auth.sign_up.return_value = MagicMock(
        user=MagicMock(id="00000000-0000-0000-0000-000000000777")
    )
    # Typed ``-> None``: the function never branches on the outcome, so an
    # identical (None) response is the non-enumeration guarantee.
    await create_signup_user(db=db_session, email="native@example.com", password="hunter22hunter22")
    mock_supabase_admin.auth.sign_up.assert_called_once_with(
        {
            "email": "native@example.com",
            "password": "hunter22hunter22",
            "options": {"email_redirect_to": get_settings().web_app_url},
        }
    )
    mock_supabase_admin.auth.resend.assert_not_called()
    mock_supabase_admin.auth.reset_password_email.assert_not_called()
    mock_supabase_admin.auth.admin.create_user.assert_not_called()


async def test_existing_unconfirmed_calls_resend_and_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Exists & unconfirmed → ``auth.resend(type=signup)``; returns ``None``."""
    _patch_gate(monkeypatch, enabled=True)
    _patch_lookup(monkeypatch, exists=True, confirmed=False)
    await create_signup_user(
        db=db_session, email="unconfirmed@example.com", password="hunter22hunter22"
    )
    mock_supabase_admin.auth.resend.assert_called_once_with(
        {
            "type": "signup",
            "email": "unconfirmed@example.com",
            "options": {"email_redirect_to": get_settings().web_app_url},
        }
    )
    mock_supabase_admin.auth.sign_up.assert_not_called()
    mock_supabase_admin.auth.reset_password_email.assert_not_called()


async def test_existing_confirmed_calls_reset_and_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Exists & confirmed → ``auth.reset_password_email`` (the "you already
    have an account" nudge) landing on /reset-password; returns ``None``."""
    _patch_gate(monkeypatch, enabled=True)
    _patch_lookup(monkeypatch, exists=True, confirmed=True)
    await create_signup_user(
        db=db_session, email="confirmed@example.com", password="hunter22hunter22"
    )
    expected_redirect = f"{get_settings().web_app_url.rstrip('/')}/reset-password"
    mock_supabase_admin.auth.reset_password_email.assert_called_once_with(
        "confirmed@example.com", {"redirect_to": expected_redirect}
    )
    mock_supabase_admin.auth.sign_up.assert_not_called()
    mock_supabase_admin.auth.resend.assert_not_called()


async def test_create_signup_user_transport_failure_maps_to_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """A ``sign_up`` transport error surfaces as EmailProviderUnavailableError (→ 502)."""
    _patch_gate(monkeypatch, enabled=True)
    _patch_lookup(monkeypatch, exists=False, confirmed=False)
    mock_supabase_admin.auth.sign_up.side_effect = httpx.ConnectError("boom")
    with pytest.raises(EmailProviderUnavailableError):
        await create_signup_user(
            db=db_session, email="down@example.com", password="hunter22hunter22"
        )


async def test_resend_confirmation_gated_off_raises_and_skips_supabase(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Hard gate also covers the standalone resend service fn."""
    _patch_gate(monkeypatch, enabled=False)
    with pytest.raises(SignupsDisabledError):
        await resend_signup_confirmation(db=db_session, email="x@example.com")
    mock_supabase_admin.auth.resend.assert_not_called()


async def test_resend_confirmation_calls_resend_and_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """Enabled → ``auth.resend(type=signup)`` with the pinned redirect."""
    _patch_gate(monkeypatch, enabled=True)
    await resend_signup_confirmation(db=db_session, email="resend@example.com")
    mock_supabase_admin.auth.resend.assert_called_once_with(
        {
            "type": "signup",
            "email": "resend@example.com",
            "options": {"email_redirect_to": get_settings().web_app_url},
        }
    )


async def test_resend_confirmation_transport_failure_maps_to_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    _patch_gate(monkeypatch, enabled=True)
    mock_supabase_admin.auth.resend.side_effect = httpx.ConnectError("boom")
    with pytest.raises(EmailProviderUnavailableError):
        await resend_signup_confirmation(db=db_session, email="down@example.com")


async def test_resend_confirmation_swallows_api_error_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """A GoTrue 4xx (e.g. already-confirmed email) is SWALLOWED → identical
    ``None`` outcome, so the resend endpoint cannot leak account state. This is
    the non-enumeration guarantee: confirmed and unconfirmed must look alike."""
    _patch_gate(monkeypatch, enabled=True)
    mock_supabase_admin.auth.resend.side_effect = AuthApiError(
        "email already confirmed", 422, "email_already_confirmed"
    )
    # Must NOT raise — swallowed to the identical no-op outcome.
    await resend_signup_confirmation(db=db_session, email="already-confirmed@example.com")


async def test_create_signup_confirmed_branch_api_error_maps_to_502_not_500(
    monkeypatch: pytest.MonkeyPatch,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    """On the main /signup path a GoTrue 4xx (NOT swallowed) collapses to
    ``EmailProviderUnavailableError`` (→ 502) — never an uncaught 500, and the
    same outcome bucket as any other branch (no 500-vs-202 oracle)."""
    _patch_gate(monkeypatch, enabled=True)
    _patch_lookup(monkeypatch, exists=True, confirmed=True)
    mock_supabase_admin.auth.reset_password_email.side_effect = AuthApiError(
        "over email send rate limit", 429, "over_email_send_rate_limit"
    )
    with pytest.raises(EmailProviderUnavailableError):
        await create_signup_user(
            db=db_session, email="throttled@example.com", password="hunter22hunter22"
        )
