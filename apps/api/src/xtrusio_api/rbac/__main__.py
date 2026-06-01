"""`python -m xtrusio_api.rbac` — run the reconciler against the reconciler role.

PAR-C M15: prefers the dedicated ``xtrusio_reconciler`` engine
(``RECONCILE_DATABASE_URL``) so the bypass GUC rides the least-privileged role.
Falls back to the request engine (``DATABASE_URL``) when the role isn't
provisioned yet, printing a warning.
"""

from __future__ import annotations

import asyncio

from ..core.db import SessionLocal
from ..core.reconciler_db import get_reconciler_sessionmaker
from .reconcile import reconcile_rbac, reconcile_user_roles_from_enums


async def _run() -> None:
    maker = get_reconciler_sessionmaker()
    if maker is None:
        maker = SessionLocal
        print("WARNING: RECONCILE_DATABASE_URL unset — reconciling on the request engine")
    async with maker() as s:
        await reconcile_rbac(s)
    async with maker() as s:
        await reconcile_user_roles_from_enums(s)
    print("rbac reconcile complete")


if __name__ == "__main__":
    asyncio.run(_run())
