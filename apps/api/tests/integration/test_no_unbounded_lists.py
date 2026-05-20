"""CI invariant: every GET list endpoint declares a query `limit` capped at MAX_LIMIT.

This is a structural test — it walks the FastAPI route table and asserts that any
handler returning a *Page model has a `limit` query param with `le=MAX_LIMIT`.
Prevents §3/§9 regressions where a future endpoint forgets pagination.
"""

from __future__ import annotations

from typing import Any

from fastapi.routing import APIRoute
from xtrusio_api.core.pagination import MAX_LIMIT
from xtrusio_api.main import app


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


def test_every_page_endpoint_has_limit_cap() -> None:
    offenders: list[str] = []
    checked: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if "GET" not in route.methods:
            continue
        rm = route.response_model
        if rm is None or not getattr(rm, "__name__", "").endswith("Page"):
            continue
        checked.append(route.path)
        params = {p.name: p for p in route.dependant.query_params}
        if "limit" not in params:
            offenders.append(f"{route.path}: missing `limit` query param")
            continue
        le = _extract_le(params["limit"].field_info)
        if le != MAX_LIMIT:
            offenders.append(f"{route.path}: limit le={le!r}, expected {MAX_LIMIT}")
    # Sanity: at least the 3 known endpoints should have been checked. If 0,
    # the introspection is wrong and the test would silently always pass.
    assert checked, "no *Page-returning GET endpoints found by route walk — introspection broken"
    assert not offenders, "Unbounded list endpoints:\n  " + "\n  ".join(offenders)
