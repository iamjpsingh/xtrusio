"""Valkey permission cache (PAR-D M16).

Exercises the cache module directly. Skips when Valkey is unreachable (the
module degrades to cache-miss/no-op in that case, which is covered implicitly by
the rest of the suite running with the cache bypassed).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from xtrusio_api.core import perm_cache

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(autouse=True)
async def _require_valkey() -> AsyncIterator[None]:
    try:
        await perm_cache._get_client().ping()  # type: ignore[misc]
    except Exception:
        pytest.skip("Valkey not reachable — perm cache degrades to bypass")
    yield


async def test_platform_roundtrip_and_invalidate() -> None:
    uid = uuid4()
    assert await perm_cache.get_platform(uid) is None
    await perm_cache.set_platform(uid, ["platform.roles.manage", "platform.users.read"])
    assert await perm_cache.get_platform(uid) == ["platform.roles.manage", "platform.users.read"]
    await perm_cache.invalidate(uid, None)
    assert await perm_cache.get_platform(uid) is None


async def test_workspace_mget_caches_empty_and_skips_unknown() -> None:
    uid, w1, w2, unknown = uuid4(), uuid4(), uuid4(), uuid4()
    await perm_cache.set_workspaces(uid, {w1: ["workspace.members.read"], w2: []})
    got = await perm_cache.get_workspaces(uid, [w1, w2, unknown])
    assert got[w1] == ["workspace.members.read"]
    assert got[w2] == []  # empty cached so an empty workspace doesn't re-query
    assert unknown not in got  # a never-set workspace is a miss, not an entry


async def test_workspace_invalidate_is_scoped() -> None:
    uid, w1, w2 = uuid4(), uuid4(), uuid4()
    await perm_cache.set_workspaces(uid, {w1: ["a"], w2: ["b"]})
    await perm_cache.invalidate(uid, w1)
    got = await perm_cache.get_workspaces(uid, [w1, w2])
    assert w1 not in got
    assert got[w2] == ["b"]  # other workspace untouched


async def test_clear_all_drops_everything() -> None:
    uid = uuid4()
    await perm_cache.set_platform(uid, ["x"])
    await perm_cache.clear_all()
    assert await perm_cache.get_platform(uid) is None
