"""Opaque cursor pagination primitive.

Cursors encode `(created_at, id)` so list queries with `ORDER BY created_at DESC, id DESC`
can resume deterministically across pages. The payload is base64url-encoded JSON;
tampering is detected on decode (we treat malformed JSON, missing keys, or invalid
type coercion as ValueError so the route can 400).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = json.dumps({"t": created_at.isoformat(), "i": str(row_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(token: str) -> tuple[datetime, UUID]:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        obj = json.loads(raw)
        return datetime.fromisoformat(obj["t"]), UUID(obj["i"])
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError("invalid cursor") from e


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
