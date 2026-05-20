"""Lifespan startup posture: fail-fast unless STARTUP_RECONCILE_TOLERANT=true."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from xtrusio_api.core.config import get_settings
from xtrusio_api.main import lifespan

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_lifespan_propagates_when_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*_: object, **__: object) -> None:
        raise RuntimeError("simulated reconcile failure")

    monkeypatch.setattr("xtrusio_api.main.reconcile_rbac", _boom)
    monkeypatch.setenv("STARTUP_RECONCILE_TOLERANT", "false")
    get_settings.cache_clear()

    try:
        with pytest.raises(RuntimeError, match="simulated"):
            async with lifespan(FastAPI()):
                pass
    finally:
        get_settings.cache_clear()


async def test_lifespan_swallows_when_tolerant(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*_: object, **__: object) -> None:
        raise RuntimeError("simulated reconcile failure")

    monkeypatch.setattr("xtrusio_api.main.reconcile_rbac", _boom)
    monkeypatch.setenv("STARTUP_RECONCILE_TOLERANT", "true")
    get_settings.cache_clear()

    try:
        async with lifespan(FastAPI()):
            pass  # should not raise
    finally:
        get_settings.cache_clear()
