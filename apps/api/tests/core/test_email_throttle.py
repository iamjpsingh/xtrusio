"""RL-2: unit tests for the Valkey-backed per-email signup throttle helper.

Needs a reachable Valkey (the throttle fails OPEN otherwise — these tests
assert the over-limit behaviour, which only holds when the backend is up). The
autouse ``_clear_email_throttle`` fixture resets the keyspace per test.
"""

from __future__ import annotations

import pytest
from xtrusio_api.core import email_throttle
from xtrusio_api.core.config import get_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def _low_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "signup_email_max_per_window", 3)
    monkeypatch.setattr(get_settings(), "signup_email_window_sec", 3600)


async def test_under_limit_not_throttled(_low_limit: None) -> None:
    email = "under-limit@example.com"
    results = [await email_throttle.is_email_throttled(email) for _ in range(3)]
    assert results == [False, False, False]


async def test_over_limit_throttled(_low_limit: None) -> None:
    email = "over-limit@example.com"
    # 3 allowed, the 4th is over the ceiling.
    for _ in range(3):
        assert await email_throttle.is_email_throttled(email) is False
    assert await email_throttle.is_email_throttled(email) is True


async def test_case_and_whitespace_share_one_bucket(_low_limit: None) -> None:
    """Case/whitespace variants must not multiply the budget (mirrors the
    case-insensitive auth.users lookup)."""
    variants = [
        "Mixed-Case@Example.com",
        "  mixed-case@example.com  ",
        "MIXED-CASE@EXAMPLE.COM",
        "mixed-case@example.com",
    ]
    results = [await email_throttle.is_email_throttled(e) for e in variants]
    # 3 allowed across the variants, the 4th (regardless of casing) is throttled.
    assert results == [False, False, False, True]


async def test_distinct_emails_are_independent(_low_limit: None) -> None:
    assert await email_throttle.is_email_throttled("a@example.com") is False
    assert await email_throttle.is_email_throttled("b@example.com") is False
    # Each still has its full budget.
    assert await email_throttle.is_email_throttled("a@example.com") is False
    assert await email_throttle.is_email_throttled("b@example.com") is False


async def test_fails_open_when_valkey_unreachable(
    monkeypatch: pytest.MonkeyPatch, _low_limit: None
) -> None:
    """A Valkey outage must NOT fail signup closed — the throttle returns False
    (the per-IP slowapi limit still applies during such an outage)."""

    class _Boom:
        def pipeline(self, *_a: object, **_k: object) -> object:
            raise ConnectionError("valkey down")

    monkeypatch.setattr(email_throttle, "_get_client", lambda: _Boom())
    for _ in range(10):
        assert await email_throttle.is_email_throttled("outage@example.com") is False
