"""Cursor pagination primitive tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from xtrusio_api.core.pagination import (
    CursorParams,
    decode_cursor,
    encode_cursor,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def test_encode_decode_round_trip() -> None:
    ts = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    rid = uuid4()
    token = encode_cursor(ts, rid)
    out_ts, out_id = decode_cursor(token)
    assert out_ts == ts
    assert out_id == rid


def test_decode_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        decode_cursor("not-a-cursor")


def test_decode_rejects_tampered() -> None:
    ts = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    token = encode_cursor(ts, uuid4())
    # Flip a character in the middle.
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(ValueError):
        decode_cursor(tampered)


def test_cursor_params_clamps_limit() -> None:
    p = CursorParams(cursor=None, limit=10_000)
    assert p.effective_limit == 200  # MAX_LIMIT
    p = CursorParams(cursor=None, limit=0)
    assert p.effective_limit == 50  # DEFAULT_LIMIT
    p = CursorParams(cursor=None, limit=75)
    assert p.effective_limit == 75
