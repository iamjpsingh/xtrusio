"""CI invariant: every GET list endpoint is bounded.

Structural test — walks the FastAPI route table and asserts:
  - any handler returning a ``*Page`` model has a ``limit`` query param capped
    at ``MAX_LIMIT``; AND
  - (PAR-D M18) no handler returns a bare ``list[...]`` / ``Sequence[...]``
    without pagination. The old matcher only checked the ``*Page`` suffix, so a
    handler typed ``-> list[FooOut]`` slipped through unbounded. Such returns
    must either page (a ``*Page`` model) or be explicitly allowlisted as a
    finite, bounded-domain list.
Prevents section 3/section 9 regressions where a future endpoint forgets pagination.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, get_origin

from fastapi.routing import APIRoute
from xtrusio_api.core.pagination import MAX_LIMIT
from xtrusio_api.main import app

# GET endpoints that intentionally return an unpaginated list because the
# domain is finite and bounded (e.g. a static catalog). Keep this empty unless
# a genuinely bounded list is added — and document why here.
_BOUNDED_LIST_ALLOWLIST: frozenset[str] = frozenset()


def _extract_le(field_info: Any) -> Any:
    """Pull the `le=` constraint off a pydantic FieldInfo, robust to FastAPI version drift."""
    # pydantic v2: metadata is a list of Annotated constraint objects (e.g., Le(le=200))
    # OR a list of fastapi.params.Query instances which carry their own attrs.
    for m in getattr(field_info, "metadata", None) or []:
        le = getattr(m, "le", None)
        if le is not None:
            return le
    # Fallback: some versions expose `le` directly on FieldInfo.
    return getattr(field_info, "le", None)


def test_every_list_endpoint_is_bounded() -> None:
    offenders: list[str] = []
    checked: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if "GET" not in route.methods:
            continue
        rm = route.response_model
        if rm is None:
            continue
        if getattr(rm, "__name__", "").endswith("Page"):
            checked.append(route.path)
            params = {p.name: p for p in route.dependant.query_params}
            if "limit" not in params:
                offenders.append(f"{route.path}: missing `limit` query param")
                continue
            le = _extract_le(params["limit"].field_info)
            if le != MAX_LIMIT:
                offenders.append(f"{route.path}: limit le={le!r}, expected {MAX_LIMIT}")
        elif get_origin(rm) in (list, Sequence) and route.path not in _BOUNDED_LIST_ALLOWLIST:
            # PAR-D M18: a bare list/Sequence return has no cursor or limit.
            checked.append(route.path)
            offenders.append(
                f"{route.path}: returns a bare {rm!r} — paginate it (*Page model) "
                "or add to _BOUNDED_LIST_ALLOWLIST with a justification"
            )
    # Sanity: at least the known *Page endpoints should have been checked. If 0,
    # the introspection is wrong and the test would silently always pass.
    assert checked, "no list-returning GET endpoints found by route walk — introspection broken"
    assert not offenders, "Unbounded list endpoints:\n  " + "\n  ".join(offenders)
