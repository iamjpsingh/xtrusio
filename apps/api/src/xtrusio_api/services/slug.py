"""Slug helpers.

The tenants table CHECK requires:
    slug ~ '^[a-z][a-z0-9-]{1,62}[a-z0-9]$'

i.e. 3-64 chars, lowercase, starts with a letter, ends alnum, hyphens in middle.
slugify() normalizes user input toward that shape; unique_slug_from_taken()
appends -2/-3/... on collision.
"""

from __future__ import annotations

import re
import unicodedata

_MAX = 64
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_LEADING_HYPHENS = re.compile(r"^-+")
_TRAILING_HYPHENS = re.compile(r"-+$")


def slugify(name: str) -> str:
    """Normalize a workspace name into a slug satisfying the tenants_slug_format CHECK."""
    ascii_lower = (
        unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode("ascii").lower()
    )
    collapsed = _NON_ALNUM.sub("-", ascii_lower)
    trimmed = _TRAILING_HYPHENS.sub("", _LEADING_HYPHENS.sub("", collapsed))
    if not trimmed or not trimmed[0].isalpha():
        if trimmed and trimmed[0].isdigit():
            trimmed = f"n{trimmed}"
        else:
            trimmed = f"tenant-{trimmed}" if trimmed else "tenant"
    # Schema regex requires 3-64 chars; pad short results.
    if len(trimmed) < 3:
        trimmed = f"tenant-{trimmed}"
    return trimmed[:_MAX]


def unique_slug_from_taken(base: str, taken: set[str]) -> str:
    """Return `base` if not taken, else `base-2`, `base-3`, ... until a free one."""
    if base not in taken:
        return base
    i = 2
    while True:
        candidate = f"{base[: _MAX - len(str(i)) - 1]}-{i}"
        if candidate not in taken:
            return candidate
        i += 1
