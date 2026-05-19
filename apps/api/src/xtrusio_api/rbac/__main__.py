"""`python -m xtrusio_api.rbac` — run the reconciler against DATABASE_URL."""

from __future__ import annotations

import asyncio

from ..core.db import SessionLocal
from .reconcile import reconcile_rbac, reconcile_user_roles_from_enums


async def _run() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    print("rbac reconcile complete")


if __name__ == "__main__":
    asyncio.run(_run())
