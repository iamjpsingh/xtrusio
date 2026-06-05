"""RL-2: per-email throttle on /api/signup + /api/signup/resend.

The secure-signup design ALWAYS sends mail, so the only pre-existing control
(an IP-keyed 5/hour slowapi limit) let an attacker rotating source IPs
email-bomb a known victim. This slice adds a second ceiling keyed on the
normalized target email, backed by Valkey.

NON-ENUMERATION is the load-bearing property under test: the 429 is purely
request-count based and fires IDENTICALLY for an existing, unconfirmed, and
non-existent email — it never branches on account state, so it adds no oracle.

Valkey dependency: these tests need a reachable Valkey (the throttle backend);
the throttle fails OPEN on a Valkey outage, so without Valkey the throttle
silently never fires and the over-limit assertions would not hold. They are
auto-tagged ``requires_supabase`` because the signup path enables signups via
the platform_settings route (touches the live engine) and uses the
``existing_super_admin`` fixture.

The autouse ``_disable_rate_limiter`` fixture turns OFF the slowapi per-IP
limit (so it can't interfere); the per-email throttle is independent of slowapi
and stays active. ``_clear_email_throttle`` resets the Valkey keys per test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from xtrusio_api.core.config import get_settings
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def _signups_enabled(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
) -> AsyncIterator[None]:
    """Flip signups ON for the test and restore OFF afterwards."""
    token = make_jwt(sub=existing_super_admin.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    try:
        yield
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )


@pytest.fixture
def _low_email_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the per-email ceiling to 2/window for a deterministic, fast test."""
    monkeypatch.setattr(get_settings(), "signup_email_max_per_window", 2)
    monkeypatch.setattr(get_settings(), "signup_email_window_sec", 3600)


async def test_signup_over_email_limit_returns_429(
    http_client: AsyncClient,
    mock_supabase_admin: MagicMock,
    _signups_enabled: None,
    _low_email_limit: None,
) -> None:
    """> limit requests to the SAME email → 429 (per-email throttle)."""
    mock_supabase_admin.auth.sign_up.return_value = MagicMock(user=MagicMock(id="x"))
    email = "bomb-target@example.com"
    body = {"email": email, "password": "Password1!"}
    r1 = await http_client.post("/api/signup", json=body)
    r2 = await http_client.post("/api/signup", json=body)
    r3 = await http_client.post("/api/signup", json=body)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r3.status_code == 429
    assert r3.json()["detail"] == "rate_limited"


async def test_different_emails_not_throttled(
    http_client: AsyncClient,
    mock_supabase_admin: MagicMock,
    _signups_enabled: None,
    _low_email_limit: None,
) -> None:
    """The throttle is PER email — distinct addresses have distinct buckets."""
    mock_supabase_admin.auth.sign_up.return_value = MagicMock(user=MagicMock(id="x"))
    # Two requests to each of two distinct emails: all within the 2/window
    # ceiling, none throttled.
    for email in ("dist-a@example.com", "dist-b@example.com"):
        body = {"email": email, "password": "Password1!"}
        assert (await http_client.post("/api/signup", json=body)).status_code == 202
        assert (await http_client.post("/api/signup", json=body)).status_code == 202


async def test_throttle_fires_identically_for_nonexistent_email(
    http_client: AsyncClient,
    mock_supabase_admin: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    _signups_enabled: None,
    _low_email_limit: None,
) -> None:
    """NON-ENUMERATION: the over-limit 429 fires the same whether or not the
    email exists. We force the existence lookup to report 'does not exist' and
    confirm the 429 still appears at the same request count (no account-state
    branch), and that the throttle short-circuits BEFORE the Supabase call."""

    async def _never_exists(_db: object, _email: str) -> tuple[bool, bool]:
        return (False, False)

    monkeypatch.setattr("xtrusio_api.services.signup.lookup_auth_user", _never_exists)
    mock_supabase_admin.auth.sign_up.return_value = MagicMock(user=MagicMock(id="x"))

    email = "ghost@example.com"
    body = {"email": email, "password": "Password1!"}
    assert (await http_client.post("/api/signup", json=body)).status_code == 202
    assert (await http_client.post("/api/signup", json=body)).status_code == 202
    r3 = await http_client.post("/api/signup", json=body)
    assert r3.status_code == 429
    assert r3.json()["detail"] == "rate_limited"
    # The 3rd (over-limit) request never reached Supabase — throttle ran first.
    assert mock_supabase_admin.auth.sign_up.call_count == 2


async def test_resend_shares_the_per_email_ceiling(
    http_client: AsyncClient,
    mock_supabase_admin: MagicMock,
    _signups_enabled: None,
    _low_email_limit: None,
) -> None:
    """/signup/resend is throttled per-email too (it's the easier bomb vector
    — no password needed)."""
    email = "resend-bomb@example.com"
    body = {"email": email}
    assert (await http_client.post("/api/signup/resend", json=body)).status_code == 202
    assert (await http_client.post("/api/signup/resend", json=body)).status_code == 202
    r3 = await http_client.post("/api/signup/resend", json=body)
    assert r3.status_code == 429
    assert r3.json()["detail"] == "rate_limited"
