"""Idempotent projection of the code catalog into the DB.

- Upserts every CATALOG entry into `permissions` (un-deprecates if it returned).
- Soft-deprecates any non-catalog `permissions` row (never deletes, never
  cascades into role_permissions — spec §4).
- Ensures every is_system role's role_permissions exactly match
  SYSTEM_ROLE_PERMISSIONS (platform roles + per-workspace roles).

Safe to run repeatedly (startup hook + `make rbac-seed` + tests).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog import CATALOG, SYSTEM_ROLE_PERMISSIONS, catalog_keys

# system-role key -> SYSTEM_ROLE_PERMISSIONS key
_PLATFORM_ROLE_MAP = {"super_admin": "super_admin", "admin": "admin"}
_WORKSPACE_ROLE_MAP = {
    "owner": "owner",
    "admin": "workspace_admin",
    "editor": "editor",
    "read_only": "read_only",
}


async def reconcile_rbac(db: AsyncSession) -> None:
    # 1. upsert catalog -> permissions
    for p in CATALOG:
        await db.execute(
            text(
                "INSERT INTO permissions (scope,key,category,description,is_deprecated) "
                "VALUES (:scope,:key,:cat,:desc,false) "
                "ON CONFLICT (key) DO UPDATE SET "
                "scope=EXCLUDED.scope, category=EXCLUDED.category, "
                "description=EXCLUDED.description, is_deprecated=false"
            ),
            {"scope": p.scope, "key": p.key, "cat": p.category, "desc": p.description},
        )

    # 2. soft-deprecate anything not in the code catalog
    await db.execute(
        text("UPDATE permissions SET is_deprecated=true WHERE NOT (key = ANY(:keys))"),
        {"keys": list(catalog_keys())},
    )

    # 3. wire platform system roles
    for role_key, map_key in _PLATFORM_ROLE_MAP.items():
        await _sync_role_perms(
            db, scope="platform", role_key=role_key,
            perm_keys=SYSTEM_ROLE_PERMISSIONS[map_key],
        )

    # 4. wire every per-workspace system role
    for role_key, map_key in _WORKSPACE_ROLE_MAP.items():
        await _sync_role_perms(
            db, scope="workspace", role_key=role_key,
            perm_keys=SYSTEM_ROLE_PERMISSIONS[map_key],
        )

    await db.commit()


async def _sync_role_perms(
    db: AsyncSession, *, scope: str, role_key: str, perm_keys: tuple[str, ...]
) -> None:
    """Make role_permissions for every is_system role with (scope,key) exactly
    equal to perm_keys. Covers platform (one row) and workspace (one per tenant).
    """
    role_ids = (
        await db.execute(
            text(
                "SELECT id FROM roles WHERE scope=:scope AND key=:key AND is_system"
            ),
            {"scope": scope, "key": role_key},
        )
    ).scalars().all()
    if not role_ids:
        return
    perm_ids = (
        await db.execute(
            text("SELECT id FROM permissions WHERE key = ANY(:keys)"),
            {"keys": list(perm_keys)},
        )
    ).scalars().all()
    for rid in role_ids:
        await db.execute(
            text("DELETE FROM role_permissions WHERE role_id=:rid"), {"rid": rid}
        )
        for pid in perm_ids:
            await db.execute(
                text(
                    "INSERT INTO role_permissions (role_id,permission_id) "
                    "VALUES (:rid,:pid) ON CONFLICT DO NOTHING"
                ),
                {"rid": rid, "pid": pid},
            )
