"""Idempotent projection of the code catalog into the DB.

- Upserts every CATALOG entry into `permissions` (un-deprecates if it returned).
- Soft-deprecates any non-catalog `permissions` row (never deletes, never
  cascades into role_permissions — spec §4).
- Ensures every is_system role's role_permissions exactly match
  SYSTEM_ROLE_PERMISSIONS (platform roles + per-workspace roles).

Safe to run repeatedly (startup hook + `make rbac-seed` + tests — both
added in Task 6). Atomic: every change is staged in one transaction and
applied by the single `db.commit()` at the end; any mid-run exception
leaves the DB untouched (all-or-nothing).
"""

from __future__ import annotations

from uuid import UUID

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
    # All statements below run in ONE transaction committed once at the end
    # (atomicity intent — do NOT move/split the commit earlier). Under
    # Postgres READ COMMITTED + MVCC the DELETE+re-INSERT in _sync_role_perms
    # is invisible to concurrent readers until this commit, so no reader ever
    # observes an empty permission set for a system role.
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
        # Full reset per role: DELETE then re-INSERT the exact target set, so
        # removing a key from the catalog also drops it from system roles.
        # `ON CONFLICT DO NOTHING` is belt-and-suspenders (nothing can collide
        # right after the same-txn DELETE) — kept for safety on re-entrancy.
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


async def wire_workspace_role_perms(db: AsyncSession, *, workspace_id: UUID) -> None:
    """Set role_permissions for ONE workspace's 4 is_system roles to match
    SYSTEM_ROLE_PERMISSIONS. SCOPED to this workspace (no all-tenants sweep)
    and does NOT commit — the caller owns the transaction. Idempotent
    (DELETE+re-INSERT for just this workspace's role ids)."""
    for role_key, map_key in _WORKSPACE_ROLE_MAP.items():
        rid = (
            await db.execute(
                text(
                    "SELECT id FROM roles WHERE scope='workspace' "
                    "AND workspace_id=:w AND key=:k AND is_system"
                ),
                {"w": workspace_id, "k": role_key},
            )
        ).scalar_one_or_none()
        if rid is None:
            continue
        perm_ids = (
            await db.execute(
                text("SELECT id FROM permissions WHERE key = ANY(:keys)"),
                {"keys": list(SYSTEM_ROLE_PERMISSIONS[map_key])},
            )
        ).scalars().all()
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


async def reconcile_user_roles_from_enums(db: AsyncSession) -> None:
    """Idempotently make every enum-era principal resolvable via the resolvers.

    Step A — close the role-ROW gap: any tenant onboarded AFTER 0006 but
    BEFORE P3a-Task-2 deployed has no workspace system role rows (the global
    reconcile_rbac only wires perms for EXISTING role rows, never creates per-
    tenant rows). Seed the 4 workspace system roles for EVERY tenant (0006
    shape + friendly name/desc, ON CONFLICT DO NOTHING) and wire each such
    workspace's role_permissions via the scoped wire_workspace_role_perms.
    Step B — project enum principals -> user_roles (the 0006 mapping, repeatable
    for rows created since): active platform super_admin/admin -> platform
    system role; every tenant_memberships row -> that workspace's matching
    system role. ON CONFLICT DO NOTHING (UNIQUE(auth_user_id,role_id,
    workspace_id)). Without Step A the Step-B workspace JOIN would silently
    skip such tenants (and live _accept_tenant would LookupError). This runs
    at startup / `make rbac-seed` only (NOT a request path), so the per-tenant
    wiring loop's O(tenants) cost is acceptable. One commit.
    """
    # Step A: seed any missing per-tenant workspace system role ROWS.
    await db.execute(
        text(
            "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
            "SELECT 'workspace', t.id, v.key, v.name, v.description, true "
            "FROM tenants t CROSS JOIN (VALUES "
            "('owner','Owner','Governs the workspace; manages roles'),"
            "('admin','Admin','Operates the workspace; cannot manage roles'),"
            "('editor','Editor','Content write access'),"
            "('read_only','Read Only','View-only access')"
            ") AS v(key, name, description) ON CONFLICT DO NOTHING"
        )
    )
    # raw db.execute() runs on the connection immediately within this txn, so
    # the seeded rows are visible to the following SELECT — no flush needed.
    tenant_ids = (
        await db.execute(text("SELECT id FROM tenants"))
    ).scalars().all()
    for tid in tenant_ids:
        await wire_workspace_role_perms(db, workspace_id=tid)
    # Step B: project enum principals -> user_roles.
    # NOT EXISTS (not just ON CONFLICT): the single-super_admin partial unique
    # index `user_roles_one_super_admin ON user_roles ((true)) WHERE role_id =
    # '...00a1'` is an EXPRESSION index, so it can never be an ON CONFLICT
    # arbiter for (auth_user_id, role_id, workspace_id). Re-attempting the
    # already-granted operator super_admin row (P1's 0006 backfill seeded it)
    # would therefore raise IntegrityError instead of no-op'ing, breaking
    # repeatability. The NOT EXISTS guard makes the projection idempotent for
    # BOTH admin and super_admin while keeping the 0006 mapping byte-identical
    # (it only ever ADDS a missing grant — zero authz-decision change).
    await db.execute(
        text(
            "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
            "SELECT pu.id, r.id, NULL, NULL FROM platform_users pu "
            "JOIN roles r ON r.scope='platform' AND r.workspace_id IS NULL "
            "  AND r.key = pu.role::text AND r.is_system "
            "WHERE pu.is_active AND pu.role::text IN ('super_admin','admin') "
            "  AND NOT EXISTS (SELECT 1 FROM user_roles ux "
            "    WHERE ux.auth_user_id = pu.id AND ux.role_id = r.id "
            "    AND ux.workspace_id IS NULL) "
            "ON CONFLICT (auth_user_id, role_id, workspace_id) DO NOTHING"
        )
    )
    await db.execute(
        text(
            "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
            "SELECT m.user_id, r.id, m.tenant_id, NULL FROM tenant_memberships m "
            "JOIN roles r ON r.scope='workspace' AND r.workspace_id = m.tenant_id "
            "  AND r.key = m.role::text AND r.is_system "
            "ON CONFLICT (auth_user_id, role_id, workspace_id) DO NOTHING"
        )
    )
    await db.commit()
