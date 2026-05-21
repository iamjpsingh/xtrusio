# RBAC P5 — Workspace RBAC Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a backend-only, per-workspace RBAC admin API — workspace role CRUD, workspace role grants (with a ≥1-owner floor invariant), and a workspace audit-log viewer — scope-isolated to one `workspace_id` and gated by the existing `workspace.*` permission catalog.

**Architecture:** Mirrors the P4 platform-admin surface (`apps/api/src/xtrusio_api/services/platform_*.py` + matching `routes/` + `schemas/`) almost line-for-line, swapping `scope='platform'` for `scope='workspace'` and adding the `workspace_id` URL segment + filter throughout. Authorization is the existing `core.permissions.require_permission(db, user_id, key, workspace_id=...)` resolver path (workspace-scoped resolves are already supported). The `≥1 active workspace owner` invariant is a brand-new service-layer pre-check on DELETE only (no DB trigger covers it). All audit writes use the existing `core.audit.write_audit_event` helper; DB priv-escalation defense-in-depth is already covered by migration `0009` which dispatches to `has_workspace_perm` whenever `workspace_id IS NOT NULL`.

**Tech Stack:** FastAPI (async), SQLAlchemy core (text SQL — same convention as P4), Pydantic v2 schemas, pytest-asyncio (session loop), httpx ASGI client. Postgres 15+ via managed Supabase.

---

## File Structure

**Service layer (new, three files mirroring `services/platform_*.py`):**
- `apps/api/src/xtrusio_api/services/workspace_roles.py` — role CRUD service (mirrors `services/platform_roles.py`).
- `apps/api/src/xtrusio_api/services/workspace_role_grants.py` — grant/revoke service (mirrors `services/platform_role_grants.py`); owns the ≥1-owner floor pre-check.
- `apps/api/src/xtrusio_api/services/workspace_audit_log.py` — audit-log list service (mirrors `services/platform_audit_log.py`).

**Schemas (new, one file; reuses `schemas/audit_log.py` for audit responses):**
- `apps/api/src/xtrusio_api/schemas/workspace_role.py` — `WorkspaceRoleIn`/`WorkspaceRolePatch`/`WorkspaceRoleOut`/`WorkspaceRolesPage`/`WorkspaceRoleGrantIn`/`WorkspaceRoleGrantOut`/`WorkspaceRoleGrantsPage`.

**Routes (new, three files mirroring `routes/platform_*.py`):**
- `apps/api/src/xtrusio_api/routes/workspace_roles.py` — `GET/POST /api/workspaces/{workspace_id}/roles`, `GET/PATCH/DELETE /api/workspaces/{workspace_id}/roles/{role_id}`.
- `apps/api/src/xtrusio_api/routes/workspace_role_grants.py` — `GET/POST /api/workspaces/{workspace_id}/members/{user_id}/roles`, `DELETE /api/workspaces/{workspace_id}/members/{user_id}/roles/{grant_id}`.
- `apps/api/src/xtrusio_api/routes/workspace_audit_log.py` — `GET /api/workspaces/{workspace_id}/audit-log`.

**Modified:**
- `apps/api/src/xtrusio_api/main.py:14-24` — add three `from .routes import workspace_*` imports.
- `apps/api/src/xtrusio_api/main.py:54-64` — `app.include_router(...)` for each new router.

**Tests (new):**
- `apps/api/tests/services/test_workspace_roles.py`
- `apps/api/tests/services/test_workspace_role_grants.py`
- `apps/api/tests/services/test_workspace_audit_log.py`
- `apps/api/tests/routes/test_workspace_roles.py`
- `apps/api/tests/routes/test_workspace_role_grants.py`
- `apps/api/tests/routes/test_workspace_audit_log.py`

**Confirmed already present (do NOT touch):**
- `apps/api/src/xtrusio_api/core/audit.py` — `write_audit_event` already accepts `workspace_id=` and `scope='workspace'`.
- `apps/api/src/xtrusio_api/core/pagination.py` — `CursorParams`, `encode_cursor`, `decode_cursor`.
- `apps/api/src/xtrusio_api/core/permissions.py:45-50` — `require_permission` already routes workspace-scoped keys through `has_workspace_perm` when `workspace_id` is passed.
- `apps/api/src/xtrusio_api/rbac/catalog.py:46-62` — all five `workspace.*` keys already present.
- `apps/api/migrations/versions/0009_rbac_governance_triggers.py:74-87` — DB priv-escalation trigger already handles workspace scope.
- `apps/api/tests/_cleanup.py:89-114` — already purges `rbac_audit_log`, `roles WHERE created_by = ANY(:ids) AND NOT is_system`, `tenant_memberships`, `tenants` for @example.com creators. Custom workspace roles tied to ephemeral @example.com creators are swept automatically.

---

## Slice A — Catalog & membership guard (foundational helpers)

The five `workspace.*` permission keys (`workspace.roles.manage`, `workspace.members.read`, `workspace.members.invite`, `workspace.members.manage`, `workspace.audit.read`) are already in `apps/api/src/xtrusio_api/rbac/catalog.py:46-62` and seeded into the DB. **No catalog change is required.** Slice A therefore contains only one task: a small membership-guard helper used by the grants service to return a friendly 404 when a `(workspace_id, user_id)` pair is not in `tenant_memberships`.

### Task A1: Membership guard helper

**Files:**
- Create: `apps/api/src/xtrusio_api/services/workspace_role_grants.py` (initial skeleton — only the helper for this task; the rest lands in Slice C)

- [ ] **Step 1: Write the failing service test for the helper**

Create `apps/api/tests/services/test_workspace_role_grants.py` with just this test:

```python
"""Service-layer tests for workspace-role grant/revoke.

Test-data hygiene: every helper uses the @example.com convention; `_cleanup.py`
sweeps all @example.com creators (auth.users, platform_users, tenants,
tenant_memberships, user_roles, rbac_audit_log, custom non-system roles).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.workspace_role_grants import (
    MembershipNotFoundError,
    _require_workspace_membership,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_tenant_with_owner() -> tuple[UUID, UUID]:
    """Seed an @example.com auth.user + tenant + tenant_memberships (owner).
    Returns (workspace_id, owner_user_id)."""
    uid, tid = uuid4(), uuid4()
    email = f"wrg-owner-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO tenants (id, slug, name, created_by) "
                "VALUES (:t,:s,:n,:u)"
            ),
            {
                "t": str(tid),
                "s": f"wrg-{tid.hex[:8]}",
                "n": "WRG tenant",
                "u": str(uid),
            },
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await s.commit()
    return tid, uid


async def test_require_membership_passes_for_member(db_session: AsyncSession) -> None:
    tid, uid = await _seed_tenant_with_owner()
    # Should not raise.
    await _require_workspace_membership(db_session, workspace_id=tid, user_id=uid)


async def test_require_membership_raises_for_non_member(db_session: AsyncSession) -> None:
    tid, _ = await _seed_tenant_with_owner()
    with pytest.raises(MembershipNotFoundError):
        await _require_workspace_membership(
            db_session, workspace_id=tid, user_id=uuid4()
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_role_grants.py -v`
Expected: `ImportError` / `ModuleNotFoundError` for `xtrusio_api.services.workspace_role_grants`.

- [ ] **Step 3: Implement the skeleton + helper**

Create `apps/api/src/xtrusio_api/services/workspace_role_grants.py`:

```python
"""Workspace-role grant/revoke service.

Mirrors `services/platform_role_grants.py` shape, scoped to one workspace.
Authorization gates (`workspace.members.read`/`workspace.members.manage`) are
the caller's responsibility (route layer via `require_permission`). This
service enforces:

- privilege-escalation pre-check against the target role's perms (friendly
  403 before the 0009 DB trigger fires; DB trigger already dispatches to
  has_workspace_perm when workspace_id IS NOT NULL).
- ≥1-active-owner floor: revoking the last workspace `owner` system-role
  grant raises OwnerFloorError (no DB trigger covers this — service-only).
- workspace-scope isolation: every read/write filters on workspace_id, so a
  grant from another workspace cannot be created, listed, or revoked here.

The caller owns the transaction (no commit here).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MembershipNotFoundError(LookupError):
    """The (workspace_id, user_id) pair is not in tenant_memberships."""


async def _require_workspace_membership(
    db: AsyncSession, *, workspace_id: UUID, user_id: UUID
) -> None:
    """Raise MembershipNotFoundError unless (workspace_id, user_id) is in
    tenant_memberships. Grants APIs use this to 404 callers who target a
    non-member — a workspace-role grant for a non-member is meaningless."""
    row = (
        await db.execute(
            text(
                "SELECT 1 FROM tenant_memberships "
                "WHERE tenant_id = :t AND user_id = :u LIMIT 1"
            ),
            {"t": str(workspace_id), "u": str(user_id)},
        )
    ).first()
    if row is None:
        raise MembershipNotFoundError(f"user {user_id} not in workspace {workspace_id}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_role_grants.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/services/workspace_role_grants.py apps/api/tests/services/test_workspace_role_grants.py
git commit -m "feat(rbac): workspace_role_grants service skeleton + membership guard"
```

---

## Slice B — Workspace role CRUD

Mirrors `services/platform_roles.py`. Differences from P4:
- Every public function takes `workspace_id: UUID`; every SQL filter pins `scope='workspace' AND workspace_id = :wid`.
- The catalog/scope check passes `scope='workspace'` to `_validate_perm_keys`.
- The `_load_role_full` query filters `r.workspace_id = :wid` in addition to id (cross-workspace isolation).
- The route gate is `workspace.roles.manage` evaluated WITH `workspace_id=workspace_id` (so it dispatches to `has_workspace_perm`).
- System role rows (`is_system=true`) for workspace scope exist (owner/admin/editor/read_only per workspace); the service-layer `SystemRoleImmutableError` guard is **load-bearing** here — migration 0009's `reject_system_role_mutation` only blocks `scope='platform'` (see `0009:118-124`), so the service is the ONLY guard against renaming a workspace `owner` role row.

### Task B1: Workspace role schemas

**Files:**
- Create: `apps/api/src/xtrusio_api/schemas/workspace_role.py`

- [ ] **Step 1: Write the schema file**

```python
"""Pydantic schemas for workspace-role endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceRoleIn(BaseModel):
    """Create-payload for a custom workspace role."""

    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permission_keys: list[str] = Field(default_factory=list)


class WorkspaceRolePatch(BaseModel):
    """Partial-update payload. None means 'leave unchanged'."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permission_keys: list[str] | None = None


class WorkspaceRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    key: str
    name: str
    description: str | None
    is_system: bool
    permission_keys: list[str]
    created_at: datetime
    updated_at: datetime


class WorkspaceRolesPage(BaseModel):
    items: list[WorkspaceRoleOut]
    next_cursor: str | None = None


class WorkspaceRoleGrantIn(BaseModel):
    """Create-payload for `POST /api/workspaces/{wid}/members/{uid}/roles`."""

    role_id: UUID


class WorkspaceRoleGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    auth_user_id: UUID
    workspace_id: UUID
    role_id: UUID
    role_key: str
    granted_at: datetime
    granted_by: UUID | None


class WorkspaceRoleGrantsPage(BaseModel):
    items: list[WorkspaceRoleGrantOut]
    next_cursor: str | None = None
```

- [ ] **Step 2: Sanity-check the schema imports**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run python -c "from xtrusio_api.schemas.workspace_role import WorkspaceRoleIn, WorkspaceRoleGrantOut; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/xtrusio_api/schemas/workspace_role.py
git commit -m "feat(rbac): workspace_role pydantic schemas"
```

### Task B2: Workspace role CRUD service — create + list + get

**Files:**
- Create: `apps/api/src/xtrusio_api/services/workspace_roles.py`
- Test: `apps/api/tests/services/test_workspace_roles.py`

- [ ] **Step 1: Write the failing service tests for create/list/get**

```python
"""Service-layer tests for workspace-role CRUD.

Actor for every test is a fresh @example.com owner of an @example.com tenant.
`_cleanup.py` sweeps everything by tenant.created_by = actor_id.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.workspace_roles import (
    RoleKeyTakenError,
    RoleNotFoundError,
    ScopeMismatchError,
    SystemRoleImmutableError,
    UnknownPermissionError,
    create_workspace_role,
    get_workspace_role,
    list_workspace_roles,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_owner_workspace() -> tuple[UUID, UUID]:
    """Seed @example.com owner + tenant + tenant_memberships(owner) +
    workspace system roles via the reconciler. Returns (workspace_id, owner_id).
    """
    uid, tid = uuid4(), uuid4()
    email = f"wsr-svc-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        # System bypass — we're seeding fixture state, not exercising auth.
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"wsr-{tid.hex[:8]}", "n": "WSR tenant", "u": str(uid)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await s.commit()

    # Boot reconciler seeds workspace system roles + projects tenant_memberships
    # -> user_roles. Do the same here so the owner actually holds owner perms.
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return tid, uid


async def test_create_workspace_role_happy_path(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    role_key = f"test_wsr_{uuid4().hex[:8]}"
    result = await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=role_key,
        name="Test Workspace Role",
        description="created by test",
        permission_keys=["workspace.members.read", "workspace.settings.read"],
    )
    await db_session.commit()
    assert result["is_system"] is False
    assert result["key"] == role_key
    assert result["scope"] == "workspace"
    assert UUID(str(result["workspace_id"])) == tid
    assert list(result["permission_keys"]) == [
        "workspace.members.read",
        "workspace.settings.read",
    ]


async def test_create_raises_role_key_taken(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    role_key = f"test_wsr_{uuid4().hex[:8]}"
    await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=role_key,
        name="First",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    with pytest.raises(RoleKeyTakenError):
        await create_workspace_role(
            db_session,
            actor_id=uid,
            workspace_id=tid,
            key=role_key,
            name="Second",
            description=None,
            permission_keys=[],
        )
    await db_session.rollback()


async def test_create_raises_unknown_permission(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    with pytest.raises(UnknownPermissionError):
        await create_workspace_role(
            db_session,
            actor_id=uid,
            workspace_id=tid,
            key=f"test_wsr_{uuid4().hex[:8]}",
            name="Bad",
            description=None,
            permission_keys=["nonexistent.fake.key"],
        )
    await db_session.rollback()


async def test_create_raises_scope_mismatch_on_platform_key(
    db_session: AsyncSession,
) -> None:
    tid, uid = await _seed_owner_workspace()
    with pytest.raises(ScopeMismatchError):
        await create_workspace_role(
            db_session,
            actor_id=uid,
            workspace_id=tid,
            key=f"test_wsr_{uuid4().hex[:8]}",
            name="Bad scope",
            description=None,
            permission_keys=["platform.users.read"],
        )
    await db_session.rollback()


async def test_list_returns_system_and_custom(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    r = await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="Custom",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    page, _ = await list_workspace_roles(db_session, workspace_id=tid, limit=200)
    keys = {row["key"] for row in page}
    # System roles seeded per-workspace in `reconcile_user_roles_from_enums`.
    assert "owner" in keys
    assert "admin" in keys
    assert "editor" in keys
    assert "read_only" in keys
    assert str(r["key"]) in keys


async def test_get_workspace_role_404_cross_workspace(
    db_session: AsyncSession,
) -> None:
    """A role from workspace A must not resolve when queried under workspace B.
    Scope-isolation regression guard."""
    tid_a, uid_a = await _seed_owner_workspace()
    tid_b, _ = await _seed_owner_workspace()
    r = await create_workspace_role(
        db_session,
        actor_id=uid_a,
        workspace_id=tid_a,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="In A",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    role_id = UUID(str(r["id"]))
    # Lookup under tid_b must 404.
    with pytest.raises(RoleNotFoundError):
        await get_workspace_role(db_session, workspace_id=tid_b, role_id=role_id)
    # But succeeds under tid_a.
    found = await get_workspace_role(db_session, workspace_id=tid_a, role_id=role_id)
    assert UUID(str(found["id"])) == role_id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_roles.py -v`
Expected: `ImportError` / `ModuleNotFoundError` for `xtrusio_api.services.workspace_roles`.

- [ ] **Step 3: Implement the service**

Create `apps/api/src/xtrusio_api/services/workspace_roles.py`:

```python
"""Workspace-role CRUD service.

Mirrors `services/platform_roles.py` shape, scoped to one workspace.

Authorization gate (`workspace.roles.manage`) is the caller's responsibility
(route layer via `require_permission(..., workspace_id=...)`). This service
enforces immutable-system-roles at the service layer because migration
`0009.reject_system_role_mutation` only blocks scope='platform' system roles —
workspace system role rows (owner/admin/editor/read_only) have is_system=true
but are NOT covered by the DB trigger. The service guard is therefore
load-bearing, not friendly-first.

The caller owns the transaction (no commit here) — matches platform_roles.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import write_audit_event
from ..core.pagination import encode_cursor


class RoleNotFoundError(LookupError):
    """The role id doesn't exist, isn't a workspace role, or belongs to
    another workspace."""


class RoleKeyTakenError(Exception):
    """A workspace role with that key already exists in this workspace."""


class SystemRoleImmutableError(Exception):
    """Caller tried to mutate a workspace system role (owner/admin/editor/
    read_only). Load-bearing — the DB trigger does not block this."""


class UnknownPermissionError(Exception):
    """A permission key is not in the catalog or is deprecated."""


class ScopeMismatchError(Exception):
    """A permission key's scope doesn't match the role's scope."""


# --- helpers ---------------------------------------------------------------


async def _set_actor(db: AsyncSession, actor_id: UUID) -> None:
    await db.execute(
        text("SELECT set_config('app.actor_id', :a, true)"),
        {"a": str(actor_id)},
    )


async def _validate_perm_keys(db: AsyncSession, *, scope: str, keys: list[str]) -> None:
    if not keys:
        return
    rows = (
        await db.execute(
            text(
                "SELECT key, scope FROM permissions "
                "WHERE key = ANY(:keys) AND NOT is_deprecated"
            ),
            {"keys": keys},
        )
    ).all()
    found = {r.key: r.scope for r in rows}
    missing = set(keys) - set(found)
    if missing:
        raise UnknownPermissionError(f"unknown or deprecated keys: {sorted(missing)}")
    wrong_scope = {k for k, s in found.items() if s != scope}
    if wrong_scope:
        raise ScopeMismatchError(f"keys not in scope={scope!r}: {sorted(wrong_scope)}")


async def _load_role_full(
    db: AsyncSession, *, workspace_id: UUID, role_id: UUID
) -> dict[str, Any] | None:
    """Load one row + aggregated permission_keys, pinning workspace_id."""
    row = (
        (
            await db.execute(
                text(
                    "SELECT r.id, r.key, r.name, r.description, r.is_system, r.scope, "
                    "r.workspace_id, r.created_at, r.updated_at, "
                    "COALESCE(("
                    "  SELECT array_agg(p.key ORDER BY p.key) "
                    "  FROM role_permissions rp "
                    "  JOIN permissions p ON p.id = rp.permission_id "
                    "  WHERE rp.role_id = r.id"
                    "), ARRAY[]::text[]) AS permission_keys "
                    "FROM roles r WHERE r.id = :id "
                    "AND r.scope = 'workspace' AND r.workspace_id = :wid"
                ),
                {"id": str(role_id), "wid": str(workspace_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


# --- public surface --------------------------------------------------------


async def create_workspace_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    key: str,
    name: str,
    description: str | None,
    permission_keys: list[str],
) -> dict[str, Any]:
    """Create a custom (is_system=False) workspace role pinned to workspace_id."""
    await _set_actor(db, actor_id)
    await _validate_perm_keys(db, scope="workspace", keys=permission_keys)
    existing = (
        await db.execute(
            text(
                "SELECT id FROM roles WHERE scope='workspace' "
                "AND workspace_id = :wid AND key = :k"
            ),
            {"wid": str(workspace_id), "k": key},
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise RoleKeyTakenError(key)
    row = (
        (
            await db.execute(
                text(
                    "INSERT INTO roles (scope, workspace_id, key, name, description, "
                    "is_system, created_by) "
                    "VALUES ('workspace', :wid, :key, :name, "
                    "COALESCE(:desc, ''), false, :actor) "
                    "RETURNING id"
                ),
                {
                    "wid": str(workspace_id),
                    "key": key,
                    "name": name,
                    "desc": description,
                    "actor": str(actor_id),
                },
            )
        )
        .mappings()
        .one()
    )
    role_id = UUID(str(row["id"]))
    if permission_keys:
        await db.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT :rid, p.id FROM permissions p "
                "WHERE p.key = ANY(:keys)"
            ),
            {"rid": str(role_id), "keys": permission_keys},
        )
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.create",
        target_type="role",
        target_id=role_id,
        scope="workspace",
        workspace_id=workspace_id,
        after={
            "key": key,
            "name": name,
            "description": description,
            "permission_keys": sorted(permission_keys),
        },
    )
    out = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    assert out is not None
    return out


async def list_workspace_roles(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """Cursor-paginated list of ALL workspace roles in this workspace
    (system + custom)."""
    base = (
        "SELECT r.id, r.key, r.name, r.description, r.is_system, r.scope, "
        "r.workspace_id, r.created_at, r.updated_at, "
        "COALESCE((SELECT array_agg(p.key ORDER BY p.key) "
        "FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
        "WHERE rp.role_id = r.id), ARRAY[]::text[]) AS permission_keys "
        "FROM roles r WHERE r.scope='workspace' AND r.workspace_id = :wid "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {"wid": str(workspace_id), "ts": ts, "rid": str(rid), "lim": limit + 1}
        sql = base + (
            "AND (r.created_at < :ts OR (r.created_at = :ts AND r.id < :rid)) "
            "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
        )
    else:
        params = {"wid": str(workspace_id), "lim": limit + 1}
        sql = base + "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last["created_at"], UUID(str(last["id"])))
        rows = rows[:limit]
    return rows, next_cursor


async def get_workspace_role(
    db: AsyncSession, *, workspace_id: UUID, role_id: UUID
) -> dict[str, Any]:
    row = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    if row is None:
        raise RoleNotFoundError(str(role_id))
    return row


async def update_workspace_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    role_id: UUID,
    name: str | None,
    description: str | None,
    permission_keys: list[str] | None,
) -> dict[str, Any]:
    """Update a custom workspace role. System roles raise SystemRoleImmutableError."""
    await _set_actor(db, actor_id)
    existing = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    if existing is None:
        raise RoleNotFoundError(str(role_id))
    if existing["is_system"]:
        raise SystemRoleImmutableError(str(role_id))
    before = {
        "name": existing["name"],
        "description": existing["description"],
        "permission_keys": list(existing["permission_keys"]),
    }
    if permission_keys is not None:
        await _validate_perm_keys(db, scope="workspace", keys=permission_keys)
    if name is not None:
        await db.execute(
            text("UPDATE roles SET name = :n, updated_at = now() WHERE id = :id"),
            {"n": name, "id": str(role_id)},
        )
    if description is not None:
        await db.execute(
            text("UPDATE roles SET description = :d, updated_at = now() WHERE id = :id"),
            {"d": description, "id": str(role_id)},
        )
    if permission_keys is not None:
        await db.execute(
            text("DELETE FROM role_permissions WHERE role_id = :rid"),
            {"rid": str(role_id)},
        )
        if permission_keys:
            await db.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT :rid, p.id FROM permissions p WHERE p.key = ANY(:keys)"
                ),
                {"rid": str(role_id), "keys": permission_keys},
            )
    after_row = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    assert after_row is not None
    after = {
        "name": after_row["name"],
        "description": after_row["description"],
        "permission_keys": list(after_row["permission_keys"]),
    }
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.update",
        target_type="role",
        target_id=role_id,
        scope="workspace",
        workspace_id=workspace_id,
        before=before,
        after=after,
    )
    return after_row


async def delete_workspace_role(
    db: AsyncSession, *, actor_id: UUID, workspace_id: UUID, role_id: UUID
) -> None:
    """Delete a custom workspace role. Cascades to role_permissions and
    user_roles via 0006 ON DELETE CASCADE. System roles raise."""
    await _set_actor(db, actor_id)
    existing = await _load_role_full(db, workspace_id=workspace_id, role_id=role_id)
    if existing is None:
        raise RoleNotFoundError(str(role_id))
    if existing["is_system"]:
        raise SystemRoleImmutableError(str(role_id))
    await db.execute(text("DELETE FROM roles WHERE id = :id"), {"id": str(role_id)})
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.delete",
        target_type="role",
        target_id=role_id,
        scope="workspace",
        workspace_id=workspace_id,
        before={
            "key": existing["key"],
            "name": existing["name"],
            "description": existing["description"],
            "permission_keys": list(existing["permission_keys"]),
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_roles.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/services/workspace_roles.py apps/api/tests/services/test_workspace_roles.py
git commit -m "feat(rbac): workspace_roles service — create/list/get/update/delete"
```

### Task B3: Update + delete service tests

**Files:**
- Modify: `apps/api/tests/services/test_workspace_roles.py` — append update/delete tests

- [ ] **Step 1: Append the failing tests**

Append to `apps/api/tests/services/test_workspace_roles.py`:

```python
async def test_update_workspace_role_happy(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import update_workspace_role

    r = await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="Before",
        description="desc-before",
        permission_keys=["workspace.members.read"],
    )
    await db_session.commit()
    role_id = UUID(str(r["id"]))
    updated = await update_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        role_id=role_id,
        name="After",
        description="desc-after",
        permission_keys=["workspace.members.read", "workspace.members.invite"],
    )
    await db_session.commit()
    assert updated["name"] == "After"
    assert updated["description"] == "desc-after"
    assert list(updated["permission_keys"]) == [
        "workspace.members.invite",
        "workspace.members.read",
    ]


async def test_update_system_role_raises(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import update_workspace_role

    owner_role_id = UUID(
        str(
            (
                await db_session.execute(
                    text(
                        "SELECT id FROM roles WHERE scope='workspace' "
                        "AND workspace_id = :w AND key='owner' AND is_system"
                    ),
                    {"w": str(tid)},
                )
            ).scalar_one()
        )
    )
    with pytest.raises(SystemRoleImmutableError):
        await update_workspace_role(
            db_session,
            actor_id=uid,
            workspace_id=tid,
            role_id=owner_role_id,
            name="renamed-owner",
            description=None,
            permission_keys=None,
        )
    await db_session.rollback()


async def test_delete_workspace_role_happy(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import delete_workspace_role

    r = await create_workspace_role(
        db_session,
        actor_id=uid,
        workspace_id=tid,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="Doomed",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    role_id = UUID(str(r["id"]))
    await delete_workspace_role(
        db_session, actor_id=uid, workspace_id=tid, role_id=role_id
    )
    await db_session.commit()
    with pytest.raises(RoleNotFoundError):
        await get_workspace_role(db_session, workspace_id=tid, role_id=role_id)


async def test_delete_system_role_raises(db_session: AsyncSession) -> None:
    tid, uid = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import delete_workspace_role

    editor_role_id = UUID(
        str(
            (
                await db_session.execute(
                    text(
                        "SELECT id FROM roles WHERE scope='workspace' "
                        "AND workspace_id = :w AND key='editor' AND is_system"
                    ),
                    {"w": str(tid)},
                )
            ).scalar_one()
        )
    )
    with pytest.raises(SystemRoleImmutableError):
        await delete_workspace_role(
            db_session, actor_id=uid, workspace_id=tid, role_id=editor_role_id
        )
    await db_session.rollback()


async def test_update_role_from_other_workspace_404s(
    db_session: AsyncSession,
) -> None:
    """Cross-workspace scope isolation — update must 404 if role lives elsewhere."""
    tid_a, uid_a = await _seed_owner_workspace()
    tid_b, _ = await _seed_owner_workspace()
    from xtrusio_api.services.workspace_roles import update_workspace_role

    r = await create_workspace_role(
        db_session,
        actor_id=uid_a,
        workspace_id=tid_a,
        key=f"test_wsr_{uuid4().hex[:8]}",
        name="In A",
        description=None,
        permission_keys=[],
    )
    await db_session.commit()
    role_id = UUID(str(r["id"]))
    with pytest.raises(RoleNotFoundError):
        await update_workspace_role(
            db_session,
            actor_id=uid_a,
            workspace_id=tid_b,
            role_id=role_id,
            name="hijack",
            description=None,
            permission_keys=None,
        )
    await db_session.rollback()
```

- [ ] **Step 2: Run the new tests to verify they pass**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_roles.py -v`
Expected: 11 passed.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/services/test_workspace_roles.py
git commit -m "test(rbac): workspace_roles update/delete + cross-workspace 404"
```

### Task B4: Workspace role CRUD routes

**Files:**
- Create: `apps/api/src/xtrusio_api/routes/workspace_roles.py`
- Modify: `apps/api/src/xtrusio_api/main.py:14-24` and `:54-64`
- Test: `apps/api/tests/routes/test_workspace_roles.py`

- [ ] **Step 1: Write the failing route tests**

```python
"""Tests for /api/workspaces/{wid}/roles CRUD."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def owner_workspace() -> AsyncIterator[tuple[UUID, UUID]]:
    """Fresh @example.com owner + tenant + system workspace roles wired.
    Yields (workspace_id, owner_user_id)."""
    uid, tid = uuid4(), uuid4()
    email = f"wsr-rt-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        # Owners must also be platform users so the JWT->CurrentUser path
        # resolves. Use the lowest-priv enum value (`editor`); the workspace
        # 'owner' grant comes from tenant_memberships projection below.
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"wsr-rt-{tid.hex[:8]}", "n": "rt", "u": str(uid)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(uid)},
        )
        await s.commit()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    try:
        yield tid, uid
    finally:
        # _cleanup.py sweeps everything tied to this @example.com user via
        # tenants.created_by, so explicit teardown is belt-and-suspenders.
        pass


@pytest_asyncio.fixture
async def member_no_role_manage() -> AsyncIterator[PlatformUser]:
    """A platform user with NO workspace grants — used for 403 tests."""
    uid = uuid4()
    email = f"wsr-rt-noperm-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        pu = PlatformUser(id=uid, email=email, role=PlatformRole.EDITOR, is_active=True)
        s.add(pu)
        await s.commit()
        await s.refresh(pu)
    yield pu


async def test_list_requires_auth(
    http_client: AsyncClient, owner_workspace: tuple[UUID, UUID]
) -> None:
    tid, _ = owner_workspace
    res = await http_client.get(f"/api/workspaces/{tid}/roles")
    assert res.status_code == 401


async def test_list_403_for_non_member(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
    member_no_role_manage: PlatformUser,
) -> None:
    tid, _ = owner_workspace
    token = make_jwt(sub=member_no_role_manage.id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/roles", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_list_200_for_owner(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.get(
        f"/api/workspaces/{tid}/roles", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    keys = {r["key"] for r in body["items"]}
    # All four workspace system roles present.
    assert {"owner", "admin", "editor", "read_only"}.issubset(keys)


async def test_create_role_201_happy(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key": "auditor_ws",
            "name": "WS Auditor",
            "description": "viewers",
            "permission_keys": ["workspace.audit.read"],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["key"] == "auditor_ws"
    assert body["is_system"] is False
    assert body["workspace_id"] == str(tid)
    assert body["permission_keys"] == ["workspace.audit.read"]


async def test_create_role_409_duplicate_key(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    headers = {"Authorization": f"Bearer {token}"}
    a = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers=headers,
        json={"key": "dup_ws", "name": "Dup", "permission_keys": []},
    )
    assert a.status_code == 201, a.text
    b = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers=headers,
        json={"key": "dup_ws", "name": "Dup 2", "permission_keys": []},
    )
    assert b.status_code == 409
    assert b.json()["detail"] == "role_key_taken"


async def test_create_role_422_unknown_perm(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"key": "bogus_ws", "name": "Bogus", "permission_keys": ["bogus.x.y"]},
    )
    assert res.status_code == 422


async def test_create_role_422_scope_mismatch(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key": "scope_ws",
            "name": "Bad scope",
            "permission_keys": ["platform.users.read"],
        },
    )
    assert res.status_code == 422


async def test_get_role_404_unknown(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.get(
        f"/api/workspaces/{tid}/roles/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "role_not_found"


async def test_patch_system_role_422(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    headers = {"Authorization": f"Bearer {token}"}
    lst = await http_client.get(f"/api/workspaces/{tid}/roles", headers=headers)
    owner = next(r for r in lst.json()["items"] if r["key"] == "owner")
    res = await http_client.patch(
        f"/api/workspaces/{tid}/roles/{owner['id']}",
        headers=headers,
        json={"name": "renamed-owner"},
    )
    assert res.status_code == 422
    assert res.json()["detail"] == "system_role_immutable"


async def test_delete_custom_role_204(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    headers = {"Authorization": f"Bearer {token}"}
    c = await http_client.post(
        f"/api/workspaces/{tid}/roles",
        headers=headers,
        json={"key": "del_me_ws", "name": "Doomed", "permission_keys": []},
    )
    assert c.status_code == 201, c.text
    rid = c.json()["id"]
    d = await http_client.delete(
        f"/api/workspaces/{tid}/roles/{rid}", headers=headers
    )
    assert d.status_code == 204
    g = await http_client.get(
        f"/api/workspaces/{tid}/roles/{rid}", headers=headers
    )
    assert g.status_code == 404


async def test_list_rejects_invalid_cursor(
    http_client: AsyncClient,
    make_jwt: Callable[..., str],
    owner_workspace: tuple[UUID, UUID],
) -> None:
    tid, uid = owner_workspace
    token = make_jwt(sub=uid)
    res = await http_client.get(
        f"/api/workspaces/{tid}/roles?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid cursor"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/routes/test_workspace_roles.py -v`
Expected: 404 on every route (no router registered yet) OR collection error.

- [ ] **Step 3: Implement the routes**

Create `apps/api/src/xtrusio_api/routes/workspace_roles.py`:

```python
"""GET/POST/PATCH/DELETE /api/workspaces/{workspace_id}/roles — workspace owner.

All endpoints gated by `workspace.roles.manage` (which workspace `owner`
holds and `workspace_admin`/`editor`/`read_only` do NOT — see
catalog.SYSTEM_ROLE_PERMISSIONS). The require_permission call passes
`workspace_id=workspace_id` so the resolver dispatches to has_workspace_perm.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.workspace_role import (
    WorkspaceRoleIn,
    WorkspaceRoleOut,
    WorkspaceRolePatch,
    WorkspaceRolesPage,
)
from ..services.workspace_roles import (
    RoleKeyTakenError,
    RoleNotFoundError,
    ScopeMismatchError,
    SystemRoleImmutableError,
    UnknownPermissionError,
    create_workspace_role,
    delete_workspace_role,
    get_workspace_role,
    list_workspace_roles,
    update_workspace_role,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspace-roles"])


@router.get("/{workspace_id}/roles", response_model=WorkspaceRolesPage)
async def list_roles(
    workspace_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> WorkspaceRolesPage:
    await require_permission(
        db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id
    )
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_workspace_roles(
        db, workspace_id=workspace_id, cursor=decoded, limit=params.effective_limit
    )
    return WorkspaceRolesPage(
        items=[WorkspaceRoleOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post(
    "/{workspace_id}/roles",
    response_model=WorkspaceRoleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_role(
    workspace_id: UUID,
    body: WorkspaceRoleIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRoleOut:
    await require_permission(
        db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id
    )
    try:
        row = await create_workspace_role(
            db,
            actor_id=user.user_id,
            workspace_id=workspace_id,
            key=body.key,
            name=body.name,
            description=body.description,
            permission_keys=body.permission_keys,
        )
        await db.commit()
    except RoleKeyTakenError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "role_key_taken") from e
    except UnknownPermissionError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except ScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return WorkspaceRoleOut.model_validate(row)


@router.get("/{workspace_id}/roles/{role_id}", response_model=WorkspaceRoleOut)
async def get_role(
    workspace_id: UUID,
    role_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRoleOut:
    await require_permission(
        db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id
    )
    try:
        row = await get_workspace_role(db, workspace_id=workspace_id, role_id=role_id)
    except RoleNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    return WorkspaceRoleOut.model_validate(row)


@router.patch("/{workspace_id}/roles/{role_id}", response_model=WorkspaceRoleOut)
async def update_role(
    workspace_id: UUID,
    role_id: UUID,
    body: WorkspaceRolePatch,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRoleOut:
    await require_permission(
        db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id
    )
    try:
        row = await update_workspace_role(
            db,
            actor_id=user.user_id,
            workspace_id=workspace_id,
            role_id=role_id,
            name=body.name,
            description=body.description,
            permission_keys=body.permission_keys,
        )
        await db.commit()
    except RoleNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    except SystemRoleImmutableError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "system_role_immutable"
        ) from e
    except UnknownPermissionError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except ScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return WorkspaceRoleOut.model_validate(row)


@router.delete(
    "/{workspace_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_role(
    workspace_id: UUID,
    role_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await require_permission(
        db, user.user_id, "workspace.roles.manage", workspace_id=workspace_id
    )
    try:
        await delete_workspace_role(
            db, actor_id=user.user_id, workspace_id=workspace_id, role_id=role_id
        )
        await db.commit()
    except RoleNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    except SystemRoleImmutableError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "system_role_immutable"
        ) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Wire the router in main.py**

In `apps/api/src/xtrusio_api/main.py`, add the import alongside the other route imports (after line 24):

```python
from .routes import workspace_roles as workspace_roles_routes
```

And the `include_router` call after the existing platform router includes (after line 60):

```python
app.include_router(workspace_roles_routes.router)
```

- [ ] **Step 5: Run the route tests to verify they pass**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/routes/test_workspace_roles.py -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/workspace_roles.py apps/api/src/xtrusio_api/main.py apps/api/tests/routes/test_workspace_roles.py
git commit -m "feat(rbac): /api/workspaces/{wid}/roles CRUD endpoints"
```

---

## Slice C — Workspace role grants

Mirrors `services/platform_role_grants.py` shape with three differences from P4:
- Every public function takes `workspace_id: UUID`; grants are pinned to it.
- The single-super_admin invariant is replaced by a **≥1-active-owner floor** check on DELETE only (counts `user_roles` workspace owner-role grants for this workspace; must remain ≥ 1 after the proposed delete).
- The DELETE SQL filters `WHERE id = :id AND auth_user_id = :user_id AND workspace_id = :wid` — this is **load-bearing scope isolation**, not polish: without it, a grant id from another workspace could be deleted via this endpoint. HANDOFF §follow-ups item flags the analogous gap on platform; P5 closes it natively at workspace scope.

### Task C1: Grant service — exceptions + grant + revoke

**Files:**
- Modify: `apps/api/src/xtrusio_api/services/workspace_role_grants.py` (the file already exists from Slice A with the membership helper; add the rest here)
- Test: `apps/api/tests/services/test_workspace_role_grants.py` (the file already exists from Slice A; append grant/revoke tests)

- [ ] **Step 1: Append the failing grant/revoke service tests**

Append to `apps/api/tests/services/test_workspace_role_grants.py`:

```python
from xtrusio_api.services.workspace_role_grants import (
    GrantNotFoundError,
    OwnerFloorError,
    PrivilegeEscalationError,
    RoleNotFoundError,
    RoleScopeMismatchError,
    grant_workspace_role,
    list_workspace_role_grants,
    revoke_workspace_role_grant,
)


async def _seed_member(workspace_id: UUID, role: str = "editor") -> UUID:
    """Add a fresh @example.com user as a tenant_memberships member of the
    given workspace. Returns the user id."""
    uid = uuid4()
    email = f"wrg-member-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, :r)"
            ),
            {"t": str(workspace_id), "u": str(uid), "r": role},
        )
        await s.commit()
    # Project to user_roles so the member actually holds the role's perms.
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return uid


async def _role_id(workspace_id: UUID, key: str, is_system: bool = True) -> UUID:
    async with SessionLocal() as s:
        rid = (
            await s.execute(
                text(
                    "SELECT id FROM roles WHERE scope='workspace' "
                    "AND workspace_id = :w AND key = :k AND is_system = :sys"
                ),
                {"w": str(workspace_id), "k": key, "sys": is_system},
            )
        ).scalar_one()
        return UUID(str(rid))


async def test_grant_happy_path(db_session: AsyncSession) -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    # Reconcile so the owner holds workspace owner perms.
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    member_id = await _seed_member(tid, "editor")
    admin_role = await _role_id(tid, "admin", is_system=True)
    result = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=member_id,
        role_id=admin_role,
    )
    await db_session.commit()
    assert result["role_key"] == "admin"
    assert UUID(str(result["auth_user_id"])) == member_id
    assert UUID(str(result["workspace_id"])) == tid


async def test_grant_404_for_non_member(db_session: AsyncSession) -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    admin_role = await _role_id(tid, "admin", is_system=True)
    with pytest.raises(MembershipNotFoundError):
        await grant_workspace_role(
            db_session,
            actor_id=owner_id,
            workspace_id=tid,
            target_user_id=uuid4(),
            role_id=admin_role,
        )
    await db_session.rollback()


async def test_grant_role_from_other_workspace_404s(db_session: AsyncSession) -> None:
    """Scope isolation — role_id from another workspace must RoleNotFoundError."""
    tid_a, owner_a = await _seed_tenant_with_owner()
    tid_b, _ = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    member_a = await _seed_member(tid_a, "editor")
    admin_role_b = await _role_id(tid_b, "admin", is_system=True)
    with pytest.raises(RoleNotFoundError):
        await grant_workspace_role(
            db_session,
            actor_id=owner_a,
            workspace_id=tid_a,
            target_user_id=member_a,
            role_id=admin_role_b,
        )
    await db_session.rollback()


async def test_grant_raises_privilege_escalation(db_session: AsyncSession) -> None:
    """An editor (no workspace.roles.manage) tries to grant the workspace
    owner role. Service raises PrivilegeEscalationError before the DB trigger
    fires."""
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    editor_id = await _seed_member(tid, "editor")
    target_id = await _seed_member(tid, "editor")
    owner_role = await _role_id(tid, "owner", is_system=True)
    with pytest.raises(PrivilegeEscalationError):
        await grant_workspace_role(
            db_session,
            actor_id=editor_id,
            workspace_id=tid,
            target_user_id=target_id,
            role_id=owner_role,
        )
    await db_session.rollback()


async def test_grant_idempotent(db_session: AsyncSession) -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    # The owner is already a member with the owner role; grant 'owner' again
    # via the API path and expect the same grant id back.
    owner_role = await _role_id(tid, "owner", is_system=True)
    a = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=owner_id,
        role_id=owner_role,
    )
    await db_session.commit()
    b = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=owner_id,
        role_id=owner_role,
    )
    await db_session.commit()
    assert UUID(str(a["id"])) == UUID(str(b["id"]))


async def test_revoke_happy_path(db_session: AsyncSession) -> None:
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    member_id = await _seed_member(tid, "editor")
    admin_role = await _role_id(tid, "admin", is_system=True)
    granted = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=member_id,
        role_id=admin_role,
    )
    await db_session.commit()
    grant_id = UUID(str(granted["id"]))
    await revoke_workspace_role_grant(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        user_id=member_id,
        grant_id=grant_id,
    )
    await db_session.commit()
    gone = (
        await db_session.execute(
            text("SELECT count(*) FROM user_roles WHERE id = :id"),
            {"id": str(grant_id)},
        )
    ).scalar_one()
    assert int(gone) == 0


async def test_revoke_owner_floor_409_when_last_owner(
    db_session: AsyncSession,
) -> None:
    """A workspace must retain ≥1 active owner grant — revoking the last
    one MUST raise OwnerFloorError."""
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    owner_grant_id = UUID(
        str(
            (
                await db_session.execute(
                    text(
                        "SELECT ur.id FROM user_roles ur "
                        "JOIN roles r ON r.id = ur.role_id "
                        "WHERE r.scope='workspace' AND r.workspace_id = :w "
                        "AND r.key='owner' AND r.is_system "
                        "AND ur.auth_user_id = :u AND ur.workspace_id = :w"
                    ),
                    {"w": str(tid), "u": str(owner_id)},
                )
            ).scalar_one()
        )
    )
    with pytest.raises(OwnerFloorError):
        await revoke_workspace_role_grant(
            db_session,
            actor_id=owner_id,
            workspace_id=tid,
            user_id=owner_id,
            grant_id=owner_grant_id,
        )
    await db_session.rollback()


async def test_revoke_owner_204_when_two_owners(db_session: AsyncSession) -> None:
    """Multiple owners allowed: with 2 owners, revoking 1 must succeed."""
    tid, owner_id = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    # Add a second member and grant them the workspace owner role explicitly
    # via the service path (priv-escalation pre-check should pass — owner_id
    # holds every workspace perm).
    second = await _seed_member(tid, "editor")
    owner_role = await _role_id(tid, "owner", is_system=True)
    g = await grant_workspace_role(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        target_user_id=second,
        role_id=owner_role,
    )
    await db_session.commit()
    grant_id = UUID(str(g["id"]))
    # Revoke the second owner — first owner remains, so the floor still holds.
    await revoke_workspace_role_grant(
        db_session,
        actor_id=owner_id,
        workspace_id=tid,
        user_id=second,
        grant_id=grant_id,
    )
    await db_session.commit()


async def test_revoke_grant_from_other_workspace_404s(
    db_session: AsyncSession,
) -> None:
    """Pass a grant_id whose workspace_id != URL workspace_id => 404."""
    tid_a, owner_a = await _seed_tenant_with_owner()
    tid_b, _ = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    member_b = await _seed_member(tid_b, "editor")
    # Find member_b's editor grant in tid_b.
    grant_b_id = UUID(
        str(
            (
                await db_session.execute(
                    text(
                        "SELECT ur.id FROM user_roles ur "
                        "JOIN roles r ON r.id = ur.role_id "
                        "WHERE r.scope='workspace' AND r.workspace_id = :w "
                        "AND ur.auth_user_id = :u"
                    ),
                    {"w": str(tid_b), "u": str(member_b)},
                )
            ).scalar_one()
        )
    )
    with pytest.raises(GrantNotFoundError):
        await revoke_workspace_role_grant(
            db_session,
            actor_id=owner_a,
            workspace_id=tid_a,
            user_id=member_b,
            grant_id=grant_b_id,
        )
    await db_session.rollback()


async def test_list_grants_filtered_to_workspace(
    db_session: AsyncSession,
) -> None:
    """List returns only this workspace's grants for this user."""
    tid_a, owner_a = await _seed_tenant_with_owner()
    tid_b, _ = await _seed_tenant_with_owner()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    # Add owner_a as a member of tid_b too (editor), so they have grants in
    # both workspaces. Listing under tid_a must return only tid_a grants.
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'editor')"
            ),
            {"t": str(tid_b), "u": str(owner_a)},
        )
        await s.commit()
    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    rows, _ = await list_workspace_role_grants(
        db_session, workspace_id=tid_a, user_id=owner_a, limit=200
    )
    assert all(UUID(str(r["workspace_id"])) == tid_a for r in rows)
    assert len(rows) >= 1  # at least the owner grant
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_role_grants.py -v`
Expected: ImportError on the new symbols (`GrantNotFoundError`, `grant_workspace_role`, ...).

- [ ] **Step 3: Implement the grant service**

Append to `apps/api/src/xtrusio_api/services/workspace_role_grants.py` (after the existing `_require_workspace_membership` helper from Slice A):

```python
from datetime import datetime
from typing import Any

from ..core.audit import write_audit_event
from ..core.pagination import encode_cursor


class RoleNotFoundError(LookupError):
    """The role id doesn't exist or isn't a role of this workspace."""


class RoleScopeMismatchError(Exception):
    """Granting/revoking a role whose scope/workspace doesn't match the URL."""


class GrantNotFoundError(LookupError):
    """The user_roles grant id doesn't exist for this (workspace_id, user_id)."""


class PrivilegeEscalationError(Exception):
    """Actor lacks at least one permission contained in the target role."""

    def __init__(self, missing_perm_key: str) -> None:
        super().__init__(f"actor lacks permission: {missing_perm_key}")
        self.missing_perm_key = missing_perm_key


class OwnerFloorError(Exception):
    """Revoking the proposed owner grant would leave the workspace with zero
    owners. A workspace MUST retain at least one active owner grant."""


async def _set_actor(db: AsyncSession, actor_id: UUID) -> None:
    await db.execute(
        text("SELECT set_config('app.actor_id', :a, true)"),
        {"a": str(actor_id)},
    )


async def _load_role(
    db: AsyncSession, *, workspace_id: UUID, role_id: UUID
) -> dict[str, Any] | None:
    row = (
        (
            await db.execute(
                text(
                    "SELECT id, scope, workspace_id, key, name, is_system "
                    "FROM roles WHERE id = :id "
                    "AND scope = 'workspace' AND workspace_id = :wid"
                ),
                {"id": str(role_id), "wid": str(workspace_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def _find_missing_workspace_perm(
    db: AsyncSession, *, actor_id: UUID, workspace_id: UUID, role_id: UUID
) -> str | None:
    """Mirror the 0009 trigger's workspace-scope branch. Return the first perm
    in the target role the actor does NOT hold in this workspace, else None."""
    row = (
        await db.execute(
            text(
                "SELECT p.key FROM role_permissions rp "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :rid "
                "AND NOT has_workspace_perm(:actor, :wid, p.key) "
                "LIMIT 1"
            ),
            {"rid": str(role_id), "actor": str(actor_id), "wid": str(workspace_id)},
        )
    ).first()
    return str(row.key) if row is not None else None


async def _count_owner_grants(db: AsyncSession, *, workspace_id: UUID) -> int:
    return int(
        (
            await db.execute(
                text(
                    "SELECT count(*) FROM user_roles ur "
                    "JOIN roles r ON r.id = ur.role_id "
                    "WHERE r.scope='workspace' AND r.workspace_id = :w "
                    "AND r.key='owner' AND r.is_system "
                    "AND ur.workspace_id = :w"
                ),
                {"w": str(workspace_id)},
            )
        ).scalar_one()
    )


async def grant_workspace_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    target_user_id: UUID,
    role_id: UUID,
) -> dict[str, Any]:
    """Grant role_id to target_user_id within workspace_id.

    Pre-checks (in order):
      1. target_user_id must be a tenant_memberships member of workspace_id
         (else MembershipNotFoundError -> 404).
      2. role_id must be a workspace-scope role belonging to this workspace
         (else RoleNotFoundError -> 404).
      3. actor must hold every perm in the target role under workspace_id
         (else PrivilegeEscalationError -> 403; defense-in-depth by 0009).

    Idempotent: re-issuing an identical grant returns the existing row.
    `user_roles` UNIQUE (auth_user_id, role_id, workspace_id) lets ON CONFLICT
    work cleanly here because workspace_id is NOT NULL for workspace grants —
    no NULLS-DISTINCT trap. We still pre-SELECT to return the existing row.
    """
    await _set_actor(db, actor_id)
    await _require_workspace_membership(db, workspace_id=workspace_id, user_id=target_user_id)
    role = await _load_role(db, workspace_id=workspace_id, role_id=role_id)
    if role is None:
        raise RoleNotFoundError(str(role_id))
    missing = await _find_missing_workspace_perm(
        db, actor_id=actor_id, workspace_id=workspace_id, role_id=role_id
    )
    if missing is not None:
        raise PrivilegeEscalationError(missing)
    existing = (
        (
            await db.execute(
                text(
                    "SELECT id, auth_user_id, role_id, workspace_id, granted_at, granted_by "
                    "FROM user_roles WHERE auth_user_id = :u AND role_id = :r "
                    "AND workspace_id = :w"
                ),
                {"u": str(target_user_id), "r": str(role_id), "w": str(workspace_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        row = existing
    else:
        row = (
            (
                await db.execute(
                    text(
                        "INSERT INTO user_roles "
                        "(auth_user_id, role_id, workspace_id, granted_by) "
                        "VALUES (:u, :r, :w, :g) "
                        "RETURNING id, auth_user_id, role_id, workspace_id, "
                        "granted_at, granted_by"
                    ),
                    {
                        "u": str(target_user_id),
                        "r": str(role_id),
                        "w": str(workspace_id),
                        "g": str(actor_id),
                    },
                )
            )
            .mappings()
            .one()
        )
    out = dict(row)
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.grant",
        target_type="user_role",
        target_id=UUID(str(out["id"])),
        scope="workspace",
        workspace_id=workspace_id,
        after={
            "auth_user_id": str(out["auth_user_id"]),
            "role_id": str(out["role_id"]),
            "role_key": role["key"],
        },
    )
    return {**out, "role_key": role["key"]}


async def revoke_workspace_role_grant(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    grant_id: UUID,
) -> None:
    """Revoke a workspace-scope grant. The lookup is pinned to
    (grant_id, user_id, workspace_id) — passing a grant id from another
    workspace or another user MUST 404 (scope isolation; not polish).

    Pre-checks (in order):
      1. grant exists with the given (id, auth_user_id, workspace_id) and is
         workspace-scope (else GrantNotFoundError -> 404).
      2. actor holds every perm in the role being revoked
         (else PrivilegeEscalationError -> 403).
      3. if the role is the workspace owner system role, revoking this grant
         must leave at least one other active owner grant in this workspace
         (else OwnerFloorError -> 409).
    """
    await _set_actor(db, actor_id)
    grant = (
        (
            await db.execute(
                text(
                    "SELECT ur.id, ur.auth_user_id, ur.role_id, ur.workspace_id, "
                    "r.scope, r.key, r.is_system "
                    "FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                    "WHERE ur.id = :id AND ur.auth_user_id = :u "
                    "AND ur.workspace_id = :w"
                ),
                {"id": str(grant_id), "u": str(user_id), "w": str(workspace_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if grant is None:
        raise GrantNotFoundError(str(grant_id))
    if grant["scope"] != "workspace":
        raise RoleScopeMismatchError(str(grant_id))
    missing = await _find_missing_workspace_perm(
        db,
        actor_id=actor_id,
        workspace_id=workspace_id,
        role_id=UUID(str(grant["role_id"])),
    )
    if missing is not None:
        raise PrivilegeEscalationError(missing)
    # ≥1-owner floor: only matters if this grant is the workspace owner system
    # role. Counting BEFORE the delete and requiring count > 1 enforces the
    # invariant under any race: a concurrent revoke could only further reduce
    # the count, but every revoke goes through this same pre-check on the same
    # row (no two txns can both pass when count=2, because the second one sees
    # count=1 after the first commit; READ COMMITTED is sufficient because the
    # actor must also hold workspace.members.manage which is owner-only).
    if grant["is_system"] and grant["key"] == "owner":
        owners = await _count_owner_grants(db, workspace_id=workspace_id)
        if owners <= 1:
            raise OwnerFloorError(str(grant_id))
    await db.execute(
        text(
            "DELETE FROM user_roles WHERE id = :id "
            "AND auth_user_id = :u AND workspace_id = :w"
        ),
        {"id": str(grant_id), "u": str(user_id), "w": str(workspace_id)},
    )
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.revoke",
        target_type="user_role",
        target_id=grant_id,
        scope="workspace",
        workspace_id=workspace_id,
        before={
            "auth_user_id": str(grant["auth_user_id"]),
            "role_id": str(grant["role_id"]),
            "role_key": grant["key"],
        },
    )


async def list_workspace_role_grants(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """List workspace-scope grants for one user in this workspace, paginated
    by (granted_at DESC, id DESC)."""
    base = (
        "SELECT ur.id, ur.auth_user_id, ur.workspace_id, ur.role_id, "
        "r.key AS role_key, ur.granted_at, ur.granted_by "
        "FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
        "WHERE ur.auth_user_id = :u AND ur.workspace_id = :w "
        "AND r.scope = 'workspace' AND r.workspace_id = :w "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {
            "u": str(user_id),
            "w": str(workspace_id),
            "ts": ts,
            "rid": str(rid),
            "lim": limit + 1,
        }
        sql = base + (
            "AND (ur.granted_at < :ts OR (ur.granted_at = :ts AND ur.id < :rid)) "
            "ORDER BY ur.granted_at DESC, ur.id DESC LIMIT :lim"
        )
    else:
        params = {"u": str(user_id), "w": str(workspace_id), "lim": limit + 1}
        sql = base + "ORDER BY ur.granted_at DESC, ur.id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last["granted_at"], UUID(str(last["id"])))
        rows = rows[:limit]
    return rows, next_cursor
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_role_grants.py -v`
Expected: 11 passed (2 from Slice A + 9 new).

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/services/workspace_role_grants.py apps/api/tests/services/test_workspace_role_grants.py
git commit -m "feat(rbac): workspace_role_grants service — grant/revoke/list + owner floor"
```

### Task C2: Workspace role grant routes

**Files:**
- Create: `apps/api/src/xtrusio_api/routes/workspace_role_grants.py`
- Modify: `apps/api/src/xtrusio_api/main.py` — add the third router import + include
- Test: `apps/api/tests/routes/test_workspace_role_grants.py`

- [ ] **Step 1: Write the failing route tests**

Create `apps/api/tests/routes/test_workspace_role_grants.py`:

```python
"""Tests for /api/workspaces/{wid}/members/{uid}/roles grant/revoke/list."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal


pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _provision_owner_and_member(
    member_role: str = "editor",
) -> tuple[UUID, UUID, UUID]:
    """Returns (workspace_id, owner_user_id, member_user_id). Both are
    @example.com users; tenant + tenant_memberships seeded; user_roles wired
    via the reconciler."""
    owner_id, tid, member_id = uuid4(), uuid4(), uuid4()
    o_email = f"wrg-rt-owner-{owner_id.hex[:8]}@example.com"
    m_email = f"wrg-rt-mem-{member_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        for uid, email in ((owner_id, o_email), (member_id, m_email)):
            await s.execute(
                text(
                    "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                    "encrypted_password, email_confirmed_at, created_at, updated_at) "
                    "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                    "'authenticated',:e,'',now(),now(),now())"
                ),
                {"id": str(uid), "e": email},
            )
            await s.execute(
                text(
                    "INSERT INTO platform_users (id, email, role, is_active) "
                    "VALUES (:id, :e, 'editor', true)"
                ),
                {"id": str(uid), "e": email},
            )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"wrg-rt-{tid.hex[:8]}", "n": "rt", "u": str(owner_id)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :o, 'owner'), (:t, :m, :r)"
            ),
            {"t": str(tid), "o": str(owner_id), "m": str(member_id), "r": member_role},
        )
        await s.commit()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return tid, owner_id, member_id


async def _role_id(workspace_id: UUID, key: str) -> UUID:
    async with SessionLocal() as s:
        rid = (
            await s.execute(
                text(
                    "SELECT id FROM roles WHERE scope='workspace' "
                    "AND workspace_id = :w AND key = :k AND is_system"
                ),
                {"w": str(workspace_id), "k": key},
            )
        ).scalar_one()
        return UUID(str(rid))


async def test_get_list_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get(
        f"/api/workspaces/{uuid4()}/members/{uuid4()}/roles"
    )
    assert res.status_code == 401


async def test_post_403_for_non_owner(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, _, member_id = await _provision_owner_and_member()
    # member_id is an editor — lacks workspace.members.manage.
    token = make_jwt(sub=member_id)
    admin_role = await _role_id(tid, "admin")
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(admin_role)},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_post_201_happy(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, member_id = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    admin_role = await _role_id(tid, "admin")
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(admin_role)},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["role_key"] == "admin"
    assert UUID(body["auth_user_id"]) == member_id
    assert UUID(body["workspace_id"]) == tid


async def test_post_404_non_member(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, _ = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    admin_role = await _role_id(tid, "admin")
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{uuid4()}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(admin_role)},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "membership_not_found"


async def test_post_404_role_not_found(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, member_id = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(uuid4())},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "role_not_found"


async def test_post_403_privilege_escalation(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """An admin (workspace_admin role; lacks workspace.roles.manage) tries to
    grant the workspace owner role. The route gate require_permission for
    workspace.members.manage passes (admin has it), but the service's
    priv-escalation pre-check sees the actor lacks workspace.roles.manage and
    returns 403."""
    tid, _, admin_actor = await _provision_owner_and_member(member_role="admin")
    token = make_jwt(sub=admin_actor)
    owner_role = await _role_id(tid, "owner")
    res = await http_client.post(
        f"/api/workspaces/{tid}/members/{admin_actor}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_id": str(owner_role)},
    )
    assert res.status_code == 403, res.text
    assert res.json()["detail"].startswith("privilege_escalation:")
    assert "workspace.roles.manage" in res.json()["detail"]


async def test_delete_204_happy(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, member_id = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    headers = {"Authorization": f"Bearer {token}"}
    admin_role = await _role_id(tid, "admin")
    post_res = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers=headers,
        json={"role_id": str(admin_role)},
    )
    assert post_res.status_code == 201, post_res.text
    grant_id = post_res.json()["id"]
    del_res = await http_client.delete(
        f"/api/workspaces/{tid}/members/{member_id}/roles/{grant_id}",
        headers=headers,
    )
    assert del_res.status_code == 204


async def test_delete_409_owner_floor(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Workspace has exactly one owner — deleting that owner grant must 409."""
    tid, owner_id, _ = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    # Find the owner's owner-role grant id.
    async with SessionLocal() as s:
        owner_grant_id = (
            await s.execute(
                text(
                    "SELECT ur.id FROM user_roles ur "
                    "JOIN roles r ON r.id = ur.role_id "
                    "WHERE r.scope='workspace' AND r.workspace_id = :w "
                    "AND r.key='owner' AND r.is_system "
                    "AND ur.auth_user_id = :u AND ur.workspace_id = :w"
                ),
                {"w": str(tid), "u": str(owner_id)},
            )
        ).scalar_one()
    res = await http_client.delete(
        f"/api/workspaces/{tid}/members/{owner_id}/roles/{owner_grant_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "owner_floor"


async def test_delete_404_cross_workspace_grant_id(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """Pass a grant_id from workspace B to a DELETE under workspace A => 404.
    Scope isolation regression guard."""
    tid_a, owner_a, _ = await _provision_owner_and_member()
    tid_b, _, member_b = await _provision_owner_and_member()
    token = make_jwt(sub=owner_a)
    # member_b has an editor grant in tid_b — fetch its id.
    async with SessionLocal() as s:
        grant_b_id = (
            await s.execute(
                text(
                    "SELECT ur.id FROM user_roles ur "
                    "JOIN roles r ON r.id = ur.role_id "
                    "WHERE r.scope='workspace' AND r.workspace_id = :w "
                    "AND ur.auth_user_id = :u"
                ),
                {"w": str(tid_b), "u": str(member_b)},
            )
        ).scalar_one()
    res = await http_client.delete(
        f"/api/workspaces/{tid_a}/members/{member_b}/roles/{grant_b_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    # member_b isn't even a member of tid_a — but require_permission only
    # checks the ACTOR's perms in tid_a. The route gate passes (owner_a has
    # workspace.members.manage in tid_a), so the service-level check fires:
    # the grant lookup pinned to (id, user_id, workspace_id=tid_a) returns
    # None => 404 grant_not_found.
    assert res.status_code == 404
    assert res.json()["detail"] == "grant_not_found"


async def test_list_paginates_with_cursor(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id, member_id = await _provision_owner_and_member()
    token = make_jwt(sub=owner_id)
    headers = {"Authorization": f"Bearer {token}"}
    # Grant 'admin' to member_id (already has editor); two grants total.
    admin_role = await _role_id(tid, "admin")
    r = await http_client.post(
        f"/api/workspaces/{tid}/members/{member_id}/roles",
        headers=headers,
        json={"role_id": str(admin_role)},
    )
    assert r.status_code == 201, r.text
    r1 = await http_client.get(
        f"/api/workspaces/{tid}/members/{member_id}/roles?limit=1", headers=headers
    )
    assert r1.status_code == 200
    p1 = r1.json()
    assert len(p1["items"]) == 1
    assert p1["next_cursor"] is not None
    r2 = await http_client.get(
        f"/api/workspaces/{tid}/members/{member_id}/roles"
        f"?limit=1&cursor={p1['next_cursor']}",
        headers=headers,
    )
    assert r2.status_code == 200
    p2 = r2.json()
    assert len(p2["items"]) == 1
    assert p1["items"][0]["id"] != p2["items"][0]["id"]


async def test_get_403_for_lacking_members_read(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    """GET is gated by workspace.members.read (held by owner, admin, editor,
    read_only — i.e., every workspace system role). Use a non-member to 403."""
    tid, _, _ = await _provision_owner_and_member()
    # Fresh non-member user.
    non_member = uuid4()
    email = f"wrg-rt-nm-{non_member.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(non_member), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(non_member), "e": email},
        )
        await s.commit()
    token = make_jwt(sub=non_member)
    res = await http_client.get(
        f"/api/workspaces/{tid}/members/{non_member}/roles",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/routes/test_workspace_role_grants.py -v`
Expected: 404 or import errors (router not yet registered).

- [ ] **Step 3: Implement the routes**

Create `apps/api/src/xtrusio_api/routes/workspace_role_grants.py`:

```python
"""GET/POST/DELETE /api/workspaces/{wid}/members/{uid}/roles.

GET gated by `workspace.members.read`; POST and DELETE gated by
`workspace.members.manage`. The service layer owns the ≥1-owner floor +
priv-escalation pre-checks (DB trigger 0009 is defense-in-depth).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT, CursorParams
from ..core.permissions import require_permission
from ..schemas.workspace_role import (
    WorkspaceRoleGrantIn,
    WorkspaceRoleGrantOut,
    WorkspaceRoleGrantsPage,
)
from ..services.workspace_role_grants import (
    GrantNotFoundError,
    MembershipNotFoundError,
    OwnerFloorError,
    PrivilegeEscalationError,
    RoleNotFoundError,
    RoleScopeMismatchError,
    grant_workspace_role,
    list_workspace_role_grants,
    revoke_workspace_role_grant,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspace-role-grants"])


@router.get(
    "/{workspace_id}/members/{user_id}/roles",
    response_model=WorkspaceRoleGrantsPage,
)
async def list_grants(
    workspace_id: UUID,
    user_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> WorkspaceRoleGrantsPage:
    await require_permission(
        db, user.user_id, "workspace.members.read", workspace_id=workspace_id
    )
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_workspace_role_grants(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        cursor=decoded,
        limit=params.effective_limit,
    )
    return WorkspaceRoleGrantsPage(
        items=[WorkspaceRoleGrantOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post(
    "/{workspace_id}/members/{user_id}/roles",
    response_model=WorkspaceRoleGrantOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_grant(
    workspace_id: UUID,
    user_id: UUID,
    body: WorkspaceRoleGrantIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceRoleGrantOut:
    await require_permission(
        db, user.user_id, "workspace.members.manage", workspace_id=workspace_id
    )
    try:
        row = await grant_workspace_role(
            db,
            actor_id=user.user_id,
            workspace_id=workspace_id,
            target_user_id=user_id,
            role_id=body.role_id,
        )
        await db.commit()
    except MembershipNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "membership_not_found") from e
    except RoleNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found") from e
    except RoleScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "role_scope_mismatch"
        ) from e
    except PrivilegeEscalationError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"privilege_escalation: {e.missing_perm_key}",
        ) from e
    return WorkspaceRoleGrantOut.model_validate(row)


@router.delete(
    "/{workspace_id}/members/{user_id}/roles/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_grant(
    workspace_id: UUID,
    user_id: UUID,
    grant_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await require_permission(
        db, user.user_id, "workspace.members.manage", workspace_id=workspace_id
    )
    try:
        await revoke_workspace_role_grant(
            db,
            actor_id=user.user_id,
            workspace_id=workspace_id,
            user_id=user_id,
            grant_id=grant_id,
        )
        await db.commit()
    except GrantNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "grant_not_found") from e
    except RoleScopeMismatchError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "role_scope_mismatch"
        ) from e
    except PrivilegeEscalationError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"privilege_escalation: {e.missing_perm_key}",
        ) from e
    except OwnerFloorError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "owner_floor") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Wire the router in main.py**

In `apps/api/src/xtrusio_api/main.py`, add the import after the existing `workspace_roles` import from Slice B:

```python
from .routes import workspace_role_grants as workspace_role_grants_routes
```

And the include alongside the previous one:

```python
app.include_router(workspace_role_grants_routes.router)
```

- [ ] **Step 5: Run the route tests to verify they pass**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/routes/test_workspace_role_grants.py -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/workspace_role_grants.py apps/api/src/xtrusio_api/main.py apps/api/tests/routes/test_workspace_role_grants.py
git commit -m "feat(rbac): /api/workspaces/{wid}/members/{uid}/roles grant/revoke endpoints"
```

---

## Slice D — Workspace audit log viewer

Mirrors `services/platform_audit_log.py` + `routes/platform_audit_log.py`. Reuses `schemas/audit_log.py` (no new schema). Differences:
- WHERE clause is `scope='workspace' AND workspace_id = :wid` (NOT `scope='platform'`).
- The audit cursor encoder/decoder is reused as-is from `services.platform_audit_log` (they're independent of scope) by importing them.

### Task D1: Workspace audit-log service

**Files:**
- Create: `apps/api/src/xtrusio_api/services/workspace_audit_log.py`
- Test: `apps/api/tests/services/test_workspace_audit_log.py`

- [ ] **Step 1: Write the failing service tests**

Create `apps/api/tests/services/test_workspace_audit_log.py`:

```python
"""Service-layer tests for the workspace audit-log viewer."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.audit import write_audit_event
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.workspace_audit_log import list_workspace_audit_events

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_actor_and_workspace() -> tuple[UUID, UUID]:
    """Seed an @example.com auth.user + tenant. Returns (actor_id, workspace_id)."""
    uid, tid = uuid4(), uuid4()
    email = f"waudit-svc-{uid.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"waudit-{tid.hex[:8]}", "n": "wa", "u": str(uid)},
        )
        await s.commit()
    return uid, tid


async def test_lists_workspace_scope_only(db_session: AsyncSession) -> None:
    actor, tid = await _seed_actor_and_workspace()
    # Write 1 platform event + 1 workspace event for same actor.
    await write_audit_event(
        db_session,
        actor_id=actor,
        action="test_p5d1_plat",
        target_type="role",
        target_id=uuid4(),
        scope="platform",
    )
    await write_audit_event(
        db_session,
        actor_id=actor,
        action="test_p5d1_ws",
        target_type="role",
        target_id=uuid4(),
        scope="workspace",
        workspace_id=tid,
    )
    await db_session.commit()
    rows, _ = await list_workspace_audit_events(
        db_session, workspace_id=tid, limit=200
    )
    mine = [r for r in rows if r["actor_auth_user_id"] == actor]
    assert len(mine) == 1
    assert mine[0]["action"] == "test_p5d1_ws"
    assert mine[0]["scope"] == "workspace"
    assert UUID(str(mine[0]["workspace_id"])) == tid


async def test_filters_to_this_workspace(db_session: AsyncSession) -> None:
    """An event in workspace B must not appear when listing workspace A."""
    actor_a, tid_a = await _seed_actor_and_workspace()
    actor_b, tid_b = await _seed_actor_and_workspace()
    await write_audit_event(
        db_session,
        actor_id=actor_a,
        action="test_p5d1_iso_a",
        target_type="role",
        target_id=uuid4(),
        scope="workspace",
        workspace_id=tid_a,
    )
    await write_audit_event(
        db_session,
        actor_id=actor_b,
        action="test_p5d1_iso_b",
        target_type="role",
        target_id=uuid4(),
        scope="workspace",
        workspace_id=tid_b,
    )
    await db_session.commit()
    rows, _ = await list_workspace_audit_events(
        db_session, workspace_id=tid_a, limit=200
    )
    actions = {r["action"] for r in rows if r["actor_auth_user_id"] in (actor_a, actor_b)}
    assert "test_p5d1_iso_a" in actions
    assert "test_p5d1_iso_b" not in actions


async def test_pagination_round_trip(db_session: AsyncSession) -> None:
    actor, tid = await _seed_actor_and_workspace()
    for i in range(3):
        await write_audit_event(
            db_session,
            actor_id=actor,
            action=f"test_p5d1_page.{i}",
            target_type="role",
            target_id=uuid4(),
            scope="workspace",
            workspace_id=tid,
        )
    await db_session.commit()
    from xtrusio_api.services.platform_audit_log import _decode_audit_cursor

    collected: list[dict[str, object]] = []
    cursor: tuple[object, int] | None = None
    safety = 0
    while safety < 50:
        rows, next_cursor = await list_workspace_audit_events(
            db_session,
            workspace_id=tid,
            cursor=cursor,  # type: ignore[arg-type]
            limit=2,
        )
        collected.extend(r for r in rows if r["actor_auth_user_id"] == actor)
        if next_cursor is None or len(collected) >= 3:
            break
        cursor = _decode_audit_cursor(next_cursor)
        safety += 1
    mine_actions = [
        str(r["action"]) for r in collected if str(r["action"]).startswith("test_p5d1_page.")
    ]
    assert set(mine_actions) == {
        "test_p5d1_page.0",
        "test_p5d1_page.1",
        "test_p5d1_page.2",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_audit_log.py -v`
Expected: ImportError on `xtrusio_api.services.workspace_audit_log`.

- [ ] **Step 3: Implement the service**

Create `apps/api/src/xtrusio_api/services/workspace_audit_log.py`:

```python
"""Workspace audit-log viewer.

Cursor-paginated SELECT on `rbac_audit_log` filtered to `scope='workspace'
AND workspace_id = :wid` so platform-scope events and other workspaces'
events are never visible at this endpoint.

Cursor encoding is identical to `services.platform_audit_log` (the audit
table's id is bigint, not uuid, so the standard core/pagination primitive
doesn't apply). We import the existing helpers rather than duplicate them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .platform_audit_log import _encode_audit_cursor  # reused — same wire format


async def list_workspace_audit_events(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    cursor: tuple[datetime, int] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """Paginated SELECT on `rbac_audit_log` where scope='workspace'
    AND workspace_id = :wid. Ordering: created_at DESC, id DESC."""
    base = (
        "SELECT id, actor_auth_user_id, action, target_type, target_id, "
        "scope, workspace_id, before, after, created_at "
        "FROM rbac_audit_log WHERE scope = 'workspace' AND workspace_id = :wid "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {"wid": str(workspace_id), "ts": ts, "rid": rid, "lim": limit + 1}
        sql = base + (
            "AND (created_at < :ts OR (created_at = :ts AND id < :rid)) "
            "ORDER BY created_at DESC, id DESC LIMIT :lim"
        )
    else:
        params = {"wid": str(workspace_id), "lim": limit + 1}
        sql = base + "ORDER BY created_at DESC, id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_audit_cursor(last["created_at"], int(last["id"]))
        rows = rows[:limit]
    return rows, next_cursor
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_audit_log.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/services/workspace_audit_log.py apps/api/tests/services/test_workspace_audit_log.py
git commit -m "feat(rbac): workspace_audit_log service — workspace-scoped cursor list"
```

### Task D2: Workspace audit-log route

**Files:**
- Create: `apps/api/src/xtrusio_api/routes/workspace_audit_log.py`
- Modify: `apps/api/src/xtrusio_api/main.py` — add the third router import + include
- Test: `apps/api/tests/routes/test_workspace_audit_log.py`

- [ ] **Step 1: Write the failing route tests**

Create `apps/api/tests/routes/test_workspace_audit_log.py`:

```python
"""Tests for GET /api/workspaces/{wid}/audit-log."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from xtrusio_api.core.audit import write_audit_event
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _provision_owner_workspace() -> tuple[UUID, UUID]:
    """Returns (workspace_id, owner_user_id). Owner holds workspace.audit.read."""
    owner_id, tid = uuid4(), uuid4()
    email = f"waudit-rt-{owner_id.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(owner_id), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(owner_id), "e": email},
        )
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:u)"),
            {"t": str(tid), "s": f"waudit-rt-{tid.hex[:8]}", "n": "wa-rt", "u": str(owner_id)},
        )
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:t, :u, 'owner')"
            ),
            {"t": str(tid), "u": str(owner_id)},
        )
        await s.commit()
    from xtrusio_api.rbac.reconcile import reconcile_user_roles_from_enums

    async with SessionLocal() as s:
        await reconcile_user_roles_from_enums(s)
    return tid, owner_id


async def _seed_event(actor_id: UUID, workspace_id: UUID, action: str) -> None:
    async with SessionLocal() as s:
        await write_audit_event(
            s,
            actor_id=actor_id,
            action=action,
            target_type="role",
            target_id=uuid4(),
            scope="workspace",
            workspace_id=workspace_id,
        )
        await s.commit()


async def test_requires_auth(http_client: AsyncClient) -> None:
    res = await http_client.get(f"/api/workspaces/{uuid4()}/audit-log")
    assert res.status_code == 401


async def test_403_for_non_member(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, _ = await _provision_owner_workspace()
    non_member = uuid4()
    email = f"waudit-rt-nm-{non_member.hex[:8]}@example.com"
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) "
                "VALUES (:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(non_member), "e": email},
        )
        await s.execute(
            text(
                "INSERT INTO platform_users (id, email, role, is_active) "
                "VALUES (:id, :e, 'editor', true)"
            ),
            {"id": str(non_member), "e": email},
        )
        await s.commit()
    token = make_jwt(sub=non_member)
    res = await http_client.get(
        f"/api/workspaces/{tid}/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "permission_denied"


async def test_200_for_owner_shape(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["items"], list)
    assert "next_cursor" in body
    for r in body["items"]:
        assert r["scope"] == "workspace"
        assert r["workspace_id"] == str(tid)


async def test_paginates_with_cursor(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id = await _provision_owner_workspace()
    for i in range(3):
        await _seed_event(owner_id, tid, f"test_p5d2_route.{i}")
    token = make_jwt(sub=owner_id)
    headers = {"Authorization": f"Bearer {token}"}
    collected: list[dict[str, object]] = []
    cursor: str | None = None
    safety = 0
    while safety < 100:
        url = f"/api/workspaces/{tid}/audit-log?limit=2"
        if cursor is not None:
            url += f"&cursor={cursor}"
        r = await http_client.get(url, headers=headers)
        assert r.status_code == 200, r.text
        page = r.json()
        collected.extend(
            row for row in page["items"]
            if str(row["action"]).startswith("test_p5d2_route.")
        )
        cursor = page["next_cursor"]
        if cursor is None or len(collected) >= 3:
            break
        safety += 1
    assert {row["action"] for row in collected} == {
        "test_p5d2_route.0",
        "test_p5d2_route.1",
        "test_p5d2_route.2",
    }


async def test_invalid_cursor_400(
    http_client: AsyncClient, make_jwt: Callable[..., str]
) -> None:
    tid, owner_id = await _provision_owner_workspace()
    token = make_jwt(sub=owner_id)
    res = await http_client.get(
        f"/api/workspaces/{tid}/audit-log?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "invalid cursor"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/routes/test_workspace_audit_log.py -v`
Expected: 404 on routes (no router registered).

- [ ] **Step 3: Implement the route**

Create `apps/api/src/xtrusio_api/routes/workspace_audit_log.py`:

```python
"""GET /api/workspaces/{workspace_id}/audit-log — workspace audit viewer.

Gated by `workspace.audit.read` (held by workspace owner; NOT held by the
other system roles per catalog.SYSTEM_ROLE_PERMISSIONS — only `owner` gets
the full `_workspace()` set; `workspace_admin` excludes `workspace.roles.manage`
but still holds `workspace.audit.read`; `editor`/`read_only` hold only
members.read + settings.read, so they 403 here).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from ..core.permissions import require_permission
from ..schemas.audit_log import AuditEventOut, AuditEventsPage
from ..services.platform_audit_log import _decode_audit_cursor  # shared encoder
from ..services.workspace_audit_log import list_workspace_audit_events

router = APIRouter(prefix="/api/workspaces", tags=["workspace-audit-log"])


@router.get("/{workspace_id}/audit-log", response_model=AuditEventsPage)
async def list_events(
    workspace_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> AuditEventsPage:
    await require_permission(
        db, user.user_id, "workspace.audit.read", workspace_id=workspace_id
    )
    effective_limit = limit if limit > 0 else DEFAULT_LIMIT
    decoded: tuple[datetime, int] | None = None
    if cursor is not None:
        try:
            decoded = _decode_audit_cursor(cursor)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_workspace_audit_events(
        db, workspace_id=workspace_id, cursor=decoded, limit=effective_limit
    )
    return AuditEventsPage(
        items=[AuditEventOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
```

- [ ] **Step 4: Wire the router in main.py**

In `apps/api/src/xtrusio_api/main.py`, add the third import:

```python
from .routes import workspace_audit_log as workspace_audit_log_routes
```

And the include:

```python
app.include_router(workspace_audit_log_routes.router)
```

After this step the imports block at the top of `main.py` will have three new `from .routes import workspace_*` lines and the `include_router` block will have three new `app.include_router(workspace_*_routes.router)` lines.

- [ ] **Step 5: Run the route tests to verify they pass**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/routes/test_workspace_audit_log.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/workspace_audit_log.py apps/api/src/xtrusio_api/main.py apps/api/tests/routes/test_workspace_audit_log.py
git commit -m "feat(rbac): GET /api/workspaces/{wid}/audit-log endpoint"
```

---

## Slice Wrap — end-of-phase checks, review, PR, HANDOFF

### Task W1: End-of-phase verification

- [ ] **Step 1: Sweep test data and run the full suite**

Run: `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make test`
Expected: every test passes, including the existing P4 + earlier-phase tests. Any new failure here means a P5 change accidentally broke a P4 invariant — fix before continuing.

- [ ] **Step 2: Run `make check` (controller-run, NOT a subagent)**

Run: `STARTUP_RECONCILE_TOLERANT=false make check`
Expected: ruff check + ruff format --check + mypy --strict + pytest + turbo lint/typecheck all green.

If `ruff format --check` reports a diff, run `make format` and re-stage; commit with `style: ruff format` and re-run `make check`.

If mypy --strict reports any error in the new files (services, routes, schemas, tests), fix in-place and commit `chore: tighten types for P5`.

- [ ] **Step 3: Spot-check by hand (optional, fast)**

Run:
```bash
STARTUP_RECONCILE_TOLERANT=false make api &
sleep 3
curl -sS http://127.0.0.1:8000/health
kill %1
```
Expected: `{"status":"ok"}` — confirms the new routers don't crash app startup.

### Task W2: Opus code-quality review

- [ ] **Step 1: Dispatch the code-review skill**

Use the `superpowers:requesting-code-review` skill against the P5 branch. Address every blocker before opening the PR; defer nits to a follow-up.

### Task W3: Open the PR

- [ ] **Step 1: Push the branch and open the PR**

Run:
```bash
git push -u origin rbac-p5-workspace-admin
gh pr create --title "P5 — Workspace RBAC admin (roles, grants, audit log)" --body "$(cat <<'EOF'
## Summary
- Workspace role CRUD: `GET/POST/PATCH/DELETE /api/workspaces/{wid}/roles[/{role_id}]` gated by `workspace.roles.manage`.
- Workspace role grants: `GET/POST /api/workspaces/{wid}/members/{uid}/roles`, `DELETE /.../{grant_id}`. GET gated by `workspace.members.read`; mutations by `workspace.members.manage`. Service-layer ≥1-active-owner floor + priv-escalation pre-check.
- Workspace audit log: `GET /api/workspaces/{wid}/audit-log` gated by `workspace.audit.read`.
- Scope isolation: every read/write filters on `workspace_id` (incl. DELETE grant by `(id, user_id, workspace_id)` — load-bearing, not polish).
- Reuses P4's `core/audit.py`, `core/pagination.py`, `core/permissions.py`, `schemas/audit_log.py`, and the 0009 governance triggers (which already handle workspace scope).

## Test plan
- [ ] `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check` is green.
- [ ] Sweep new service tests: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_*.py -v`.
- [ ] Sweep new route tests: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/routes/test_workspace_*.py -v`.
- [ ] Manual smoke: `make api` + curl `/health`.
EOF
)"
```
Expected: a PR URL printed to stdout. **No Co-Authored-By trailer** (per `feedback_no_claude_coauthor` memory).

### Task W4: Merge + HANDOFF update

- [ ] **Step 1: Merge once reviewed**

Use the GitHub UI or `gh pr merge --merge --delete-branch`.

- [ ] **Step 2: Update `docs/superpowers/HANDOFF.md`**

Mark P5 as merged in the status header and shift the NEXT pointer to P6b. Drop the redundant "P5 still TODO" line from §NEXT item 2. Commit:

```bash
git checkout main
git pull --ff-only
# edit docs/superpowers/HANDOFF.md
git add docs/superpowers/HANDOFF.md
git commit -m "docs(handoff): mark P5 (workspace RBAC admin) merged; pivot to P6b"
git push
```

---

## Self-Review Notes

**Spec coverage:** all three P5 surfaces — workspace role CRUD (Slice B), workspace role grants with ≥1-owner floor (Slice C), workspace audit-log viewer (Slice D) — each have service-layer tests, route-layer tests, and a registered router. Scope isolation is covered by explicit tests (`test_get_workspace_role_404_cross_workspace`, `test_update_role_from_other_workspace_404s`, `test_grant_role_from_other_workspace_404s`, `test_delete_404_cross_workspace_grant_id`, `test_filters_to_this_workspace`).

**Catalog confirmation:** all five `workspace.*` keys exist in `apps/api/src/xtrusio_api/rbac/catalog.py:46-62`. Slice A required no catalog change — the membership-guard helper is the only foundational addition.

**Patterns mirrored from P4 (shape, not text):**
- Service exception shape (one custom Exception per surface), `_set_actor` GUC pattern, `await write_audit_event` in the same tx as the mutation, caller-owns-tx convention — all mirror `services/platform_roles.py:56-65` and `services/platform_role_grants.py:65-73`.
- Route exception-translation block (try/except per error → HTTPException with stable `detail` string) mirrors `routes/platform_roles.py:78-86`.
- Cursor pagination uses the shared primitive for role lists (uuid id) and the dedicated bigint cursor in `services.platform_audit_log` for audit lists.

**Deliberate deviations from P4:**
1. **No `single_super_admin` analogue.** Workspace owners are not capped; the floor invariant is the *opposite* (≥1, not ≤1) and is enforced only on revoke. New exception `OwnerFloorError` + 409 `owner_floor` detail.
2. **Membership guard on grants.** P4 grant against `platform_users.id` returns `PlatformUserNotFoundError` (404) when the row doesn't exist. P5 needs an analogous "is this principal even in this workspace?" check — new `MembershipNotFoundError` + 404 `membership_not_found`. Without it, you could `POST /api/workspaces/{wid}/members/{uid}/roles` for a uid that's never been onboarded to wid, and the grant would silently succeed (because `user_roles` has no FK to `tenant_memberships`).
3. **DELETE pinned on `(id, user_id, workspace_id)`.** P4's `revoke_platform_role_grant` deletes by id only — safe at platform scope because there's no workspace dimension. P5's DELETE filter is load-bearing scope isolation per the spec's call-out; without it a workspace A owner could revoke a grant from workspace B by knowing its uuid.
4. **Service-layer `SystemRoleImmutableError` is load-bearing here, not friendly-first.** Migration 0009's `reject_system_role_mutation` only blocks `scope='platform'` (see `0009:118-124`). The workspace system roles (owner/admin/editor/read_only per workspace) have `is_system=true` but no DB-level immutability trigger — the service guard is the only protection. Documented in the service docstring.

**Placeholder scan:** zero "TBD"/"similar to Task N"/"implement later" markers. Every step shows actual code or actual commands.

**Type consistency:** `OwnerFloorError`, `MembershipNotFoundError`, `grant_workspace_role`, `revoke_workspace_role_grant`, `list_workspace_role_grants` — same names everywhere they appear (route, service, tests).

**Env requirement:** every `uv run pytest` invocation is prefixed with `STARTUP_RECONCILE_TOLERANT=false`. `make check`/`make test`/`make test-clean` invocations are too.
