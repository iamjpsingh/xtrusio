"""Tests for GET /api/audit/catalog.

Authenticated but ungated — every logged-in caller gets the same non-secret
event catalog (mirrors /api/permissions/catalog). Asserts: 401 unauthenticated,
200 + shape, and that the payload matches the in-process catalog data.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from httpx import AsyncClient
from xtrusio_api.core.audit_catalog import actions, categories
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_catalog_unauthenticated_401(http_client: AsyncClient) -> None:
    resp = await http_client.get("/api/audit/catalog")
    assert resp.status_code == 401


async def test_catalog_returns_full_catalog(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    resp = await http_client.get(
        "/api/audit/catalog",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"categories", "actions"}

    cat_keys = {c["key"] for c in body["categories"]}
    assert cat_keys == {k for k, _ in categories()}

    action_map = {a["action"]: (a["label"], a["category"]) for a in body["actions"]}
    expected = {action: (label, cat) for action, label, cat in actions()}
    assert action_map == expected


async def test_catalog_shape_conforms(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    existing_super_admin: PlatformUser,
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    body = (
        await http_client.get(
            "/api/audit/catalog",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()
    for c in body["categories"]:
        assert set(c.keys()) == {"key", "label"}
        assert isinstance(c["key"], str) and c["key"]
        assert isinstance(c["label"], str) and c["label"]
    valid_categories = {k for k, _ in categories()}
    for a in body["actions"]:
        assert set(a.keys()) == {"action", "label", "category"}
        assert isinstance(a["action"], str) and a["action"]
        assert isinstance(a["label"], str) and a["label"]
        assert a["category"] in valid_categories
