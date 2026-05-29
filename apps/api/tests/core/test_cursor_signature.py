"""HMAC-signed pagination cursors (PAR-D M5).

Pure-function tests against ``core.pagination`` — no DB. The signing key comes
from settings (``CURSOR_HMAC_KEY`` in the test ``.env``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from xtrusio_api.core.pagination import decode_cursor, encode_cursor


def test_roundtrip_preserves_ts_and_id() -> None:
    ts = datetime(2026, 5, 1, 12, 30, 45, 123456, tzinfo=UTC)
    rid = uuid4()
    out_ts, out_id = decode_cursor(encode_cursor(ts, rid))
    assert out_ts == ts
    assert out_id == rid


def test_tampered_payload_rejected() -> None:
    token = encode_cursor(datetime(2026, 1, 1, tzinfo=UTC), uuid4())
    # Flip a character near the start (inside the signed JSON payload).
    flipped = ("A" if token[0] != "A" else "B") + token[1:]
    with pytest.raises(ValueError):
        decode_cursor(flipped)


def test_truncated_signature_rejected() -> None:
    token = encode_cursor(datetime(2026, 1, 1, tzinfo=UTC), uuid4())
    with pytest.raises(ValueError):
        decode_cursor(token[:-4])


def test_unsigned_legacy_cursor_rejected() -> None:
    # A pre-PAR-D cursor was base64url(json) with no ``.<sig>`` suffix.
    import base64
    import json

    raw = json.dumps(
        {"t": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "i": str(uuid4())}
    ).encode()
    legacy = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    with pytest.raises(ValueError):
        decode_cursor(legacy)


def test_future_timestamp_rejected_even_when_signed() -> None:
    # A correctly-signed cursor with a ts beyond now+skew must still be rejected:
    # a legitimate cursor can only reference an already-created row.
    future = datetime.now(UTC) + timedelta(hours=1)
    token = encode_cursor(future, uuid4())
    with pytest.raises(ValueError):
        decode_cursor(token)


def test_now_timestamp_accepted() -> None:
    # Just-now (within skew) must round-trip — it's a legitimate fresh cursor.
    now = datetime.now(UTC)
    rid = uuid4()
    out_ts, out_id = decode_cursor(encode_cursor(now, rid))
    assert out_id == rid
    assert out_ts == now
