"""Opaque, HMAC-signed cursor pagination primitive.

Cursors encode `(created_at, id)` so list queries with `ORDER BY created_at DESC, id DESC`
can resume deterministically across pages.

PAR-D M5: the payload is base64url(`<json>.<sig>`) where ``sig`` is an
HMAC-SHA256 over the JSON keyed by ``settings.cursor_hmac_key``. Decode
verifies the signature in constant time and rejects tampered or forged
cursors (malformed JSON, bad signature, missing keys, or a future timestamp
all raise ValueError so the route can 400). A future timestamp is rejected
because a legitimate cursor can only ever reference a row that already exists
(`created_at <= now`); allowing one lets a forged cursor probe arbitrary
windows.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from .config import get_settings

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
# Small allowance so minor client/server clock skew on a just-created row's
# cursor doesn't trip the `ts <= now` guard.
_FUTURE_SKEW = timedelta(seconds=5)


def _sign(raw: bytes) -> str:
    key = get_settings().cursor_hmac_key.encode("utf-8")
    return hmac.new(key, raw, hashlib.sha256).hexdigest()[:16]


def encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = json.dumps({"t": created_at.isoformat(), "i": str(row_id)}).encode("utf-8")
    signed = raw + b"." + _sign(raw).encode("ascii")
    return base64.urlsafe_b64encode(signed).rstrip(b"=").decode("ascii")


def decode_cursor(token: str) -> tuple[datetime, UUID]:
    try:
        padded = token + "=" * (-len(token) % 4)
        signed = base64.urlsafe_b64decode(padded.encode("ascii"))
        raw, _, sig = signed.rpartition(b".")
        if not raw or not hmac.compare_digest(sig.decode("ascii"), _sign(raw)):
            raise ValueError("cursor signature mismatch")
        obj = json.loads(raw)
        ts = datetime.fromisoformat(obj["t"])
        row_id = UUID(obj["i"])
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError("invalid cursor") from e
    now = datetime.now(UTC)
    # Normalise naive timestamps to UTC for the comparison (stored values are
    # tz-aware, but be defensive against a forged naive payload).
    ts_cmp = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
    if ts_cmp > now + _FUTURE_SKEW:
        raise ValueError("invalid cursor")
    return ts, row_id


@dataclass(frozen=True)
class CursorParams:
    cursor: str | None
    limit: int

    @property
    def effective_limit(self) -> int:
        if self.limit <= 0:
            return DEFAULT_LIMIT
        return min(self.limit, MAX_LIMIT)

    def decoded(self) -> tuple[datetime, UUID] | None:
        if self.cursor is None:
            return None
        return decode_cursor(self.cursor)
