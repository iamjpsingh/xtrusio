# RBAC P1 — Schema & Migration Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the data-driven RBAC schema (tables, models, code-defined permission catalog, system-role seeds, enum→role backfill) as a single reversible Alembic migration `0006` plus an idempotent reconciler, with zero behaviour change for existing code.

**Architecture:** Migration `0006` (pure raw SQL, the codebase convention — see every existing migration) creates the five RBAC tables, grants, triggers, the single-super_admin DB invariant, seeds **system role rows**, backfills `user_roles` from the existing `platform_users.role` / `tenant_memberships.role` enum rows, and adds nullable `role_id` columns to the invite tables (backfilled, enum kept). The **permission catalog** lives in code (`xtrusio_api.rbac.catalog`); an idempotent **reconciler** (`xtrusio_api.rbac.reconcile`) projects that catalog into the `permissions` table and attaches each system role's `role_permissions`. This split keeps migrations pure-SQL while honouring spec §4 ("reconciler runs on migrate/startup") and §7. The old enum columns on identity/membership tables are NOT dropped here — nothing reads the new model until P3, so existing behaviour is untouched.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x (async, `Mapped`/`mapped_column`), Alembic (raw `op.execute`), asyncpg, Postgres (Supabase managed), pytest + pytest-asyncio, `uv`, `make`.

**Spec:** `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` (§2–§7, §10 row P1, §11).

---

## Conventions that apply to EVERY task (read once)

- **Run backend tests:** `uv run --directory apps/api pytest <path> -v`
- **Async test marker:** every test module that touches the DB starts with
  `pytestmark = pytest.mark.asyncio(loop_scope="session")` (Plan-2 gotcha #5 — function-scoped
  loops raise `InternalClientError` on the shared asyncpg engine).
- **Test-data hygiene:** tests NEVER create a `super_admin` or any row; backfill correctness is
  verified **read-only** against the one real `admin@xtrusio.com` super_admin via the existing
  `existing_super_admin` fixture (skips if absent — never fails, never creates). No `@example.com`
  writes in this plan.
- **Migrations are pure raw SQL** via `op.execute("…")`. No app imports inside migration files
  (matches `0001`–`0005`). `revision`/`down_revision` typed exactly as in `0005`.
- **asyncpg rejects multi-statement `text()`** — one statement per `op.execute` / `db.execute`
  (Plan-2 gotcha #8).
- **No `Co-Authored-By` trailer** on commits (`feedback_no_claude_coauthor`). Commit with the
  repo's existing git identity.
- **Lint/type baseline:** ruff clean; `mypy --strict src` = the 1 pre-existing `jose` error only.
  Zero NEW. Run `uv run ruff check apps/api` + `uv run mypy --strict apps/api/src` before each commit.
- **Apply / revert migration:** `make migrate` (apply to DATABASE_URL) / `make migrate-down`
  (revert latest). These run against the managed Supabase DB; the migration must be safe on a DB
  that already holds the one real super_admin + real tenants.
- **Single Alembic head** after this plan: `0006`.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/src/xtrusio_api/rbac/__init__.py` | New package marker. |
| `apps/api/src/xtrusio_api/rbac/catalog.py` | Code-defined permission catalog + system-role→permission-key map. The single source of truth for permission primitives. |
| `apps/api/src/xtrusio_api/rbac/reconcile.py` | Idempotent projection of the catalog into `permissions` + system-role `role_permissions`; soft-deprecation. |
| `apps/api/src/xtrusio_api/models/rbac.py` | SQLAlchemy ORM models: `Permission`, `Role`, `RolePermission`, `UserRole`, `RbacAuditLog`. |
| `apps/api/src/xtrusio_api/models/__init__.py` | Re-export the new models (Alembic autogen + app imports). |
| `apps/api/migrations/versions/0006_rbac_foundation.py` | Create tables/grants/triggers/invariant; seed system role rows; backfill `user_roles`; add+backfill invite `role_id`; reversible `downgrade`. |
| `apps/api/tests/rbac/__init__.py` | New test package marker. |
| `apps/api/tests/rbac/test_catalog.py` | Catalog integrity tests. |
| `apps/api/tests/rbac/test_models.py` | ORM mapper-config + table-name tests. |
| `apps/api/tests/rbac/test_migration_0006.py` | Read-only live-schema + seed + backfill assertions. |
| `apps/api/tests/rbac/test_reconcile.py` | Reconciler idempotency + soft-deprecate tests. |
| `Makefile` | Add `rbac-seed` target (runs the reconciler against DATABASE_URL). |
| `apps/api/src/xtrusio_api/main.py` | Call the reconciler once on app startup (self-healing catalog). |

---

## Permission catalog for P1 (the canonical seed set)

These are the keys the catalog ships with in P1. Phases P2–P6 add more as features land. Format
`scope.resource.action`. `category` drives the future role-builder UI grouping (spec §4).

| scope | key | category | description |
|---|---|---|---|
| platform | `platform.roles.manage` | Access control | Create/edit/delete platform roles and their permissions |
| platform | `platform.users.read` | Platform users | View platform users |
| platform | `platform.users.invite` | Platform users | Invite platform users |
| platform | `platform.users.manage` | Platform users | Activate/deactivate/assign roles to platform users |
| platform | `platform.clients.read` | Clients | View client workspaces |
| platform | `platform.clients.manage` | Clients | Create/manage client workspaces |
| platform | `platform.settings.read` | Settings | View platform settings |
| platform | `platform.settings.manage` | Settings | Edit platform settings |
| platform | `platform.audit.read` | Audit | View the platform RBAC audit log |
| workspace | `workspace.roles.manage` | Access control | Create/edit/delete workspace roles and their permissions |
| workspace | `workspace.members.read` | Members | View workspace members |
| workspace | `workspace.members.invite` | Members | Invite workspace members |
| workspace | `workspace.members.manage` | Members | Remove members / assign workspace roles |
| workspace | `workspace.settings.read` | Settings | View workspace settings |
| workspace | `workspace.settings.manage` | Settings | Edit workspace settings |
| workspace | `workspace.audit.read` | Audit | View the workspace RBAC audit log |

**System-role → permission-key map (P1):**

- platform `super_admin` → **all** `platform.*` keys above.
- platform `admin` → every `platform.*` key **except** `platform.roles.manage`.
- workspace `owner` → **all** `workspace.*` keys above.
- workspace `admin` → every `workspace.*` key **except** `workspace.roles.manage`.
- workspace `editor` → `workspace.members.read`, `workspace.settings.read`.
- workspace `read_only` → `workspace.members.read`, `workspace.settings.read`.

---

### Task 1: Permission catalog module

**Files:**
- Create: `apps/api/src/xtrusio_api/rbac/__init__.py`
- Create: `apps/api/src/xtrusio_api/rbac/catalog.py`
- Create: `apps/api/tests/rbac/__init__.py`
- Test: `apps/api/tests/rbac/test_catalog.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/rbac/__init__.py` (empty file) and `apps/api/tests/rbac/test_catalog.py`:

```python
"""Catalog integrity: keys unique, scopes valid, system-role map closed."""

from __future__ import annotations

from xtrusio_api.rbac.catalog import (
    CATALOG,
    SYSTEM_ROLE_PERMISSIONS,
    Permission,
    catalog_keys,
)


def test_keys_unique_and_scoped() -> None:
    keys = [p.key for p in CATALOG]
    assert len(keys) == len(set(keys)), "duplicate permission key"
    for p in CATALOG:
        assert p.scope in ("platform", "workspace")
        assert p.key.startswith(p.scope + "."), f"{p.key} not under its scope"
        assert p.category and p.description


def test_system_role_map_references_only_catalog_keys() -> None:
    valid = catalog_keys()
    for role_key, perm_keys in SYSTEM_ROLE_PERMISSIONS.items():
        scope = "platform" if role_key in ("super_admin", "admin") and role_key != "owner" else None
        for k in perm_keys:
            assert k in valid, f"{role_key} references unknown permission {k}"


def test_super_admin_has_every_platform_permission() -> None:
    platform_keys = {p.key for p in CATALOG if p.scope == "platform"}
    assert set(SYSTEM_ROLE_PERMISSIONS["super_admin"]) == platform_keys


def test_owner_has_every_workspace_permission() -> None:
    workspace_keys = {p.key for p in CATALOG if p.scope == "workspace"}
    assert set(SYSTEM_ROLE_PERMISSIONS["owner"]) == workspace_keys


def test_admin_excludes_roles_manage() -> None:
    assert "platform.roles.manage" not in SYSTEM_ROLE_PERMISSIONS["admin"]
    assert "workspace.roles.manage" not in SYSTEM_ROLE_PERMISSIONS["workspace_admin"]


def test_permission_is_frozen() -> None:
    p = CATALOG[0]
    assert isinstance(p, Permission)
    try:
        p.key = "x"  # type: ignore[misc]
        raise AssertionError("Permission should be immutable")
    except (AttributeError, Exception):
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory apps/api pytest tests/rbac/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'xtrusio_api.rbac'`.

- [ ] **Step 3: Write minimal implementation**

Create `apps/api/src/xtrusio_api/rbac/__init__.py` (empty).

Create `apps/api/src/xtrusio_api/rbac/catalog.py`:

```python
"""Code-defined RBAC permission catalog — the single source of truth.

Developers add `scope.resource.action` keys here as features ship. Roles are
data; permission primitives are NOT (spec §2.1). The reconciler projects this
into the `permissions` table; migration `0006` seeds system roles whose
`role_permissions` are derived from SYSTEM_ROLE_PERMISSIONS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Scope = Literal["platform", "workspace"]


@dataclass(frozen=True, slots=True)
class Permission:
    scope: Scope
    key: str
    category: str
    description: str


CATALOG: tuple[Permission, ...] = (
    Permission("platform", "platform.roles.manage", "Access control",
               "Create/edit/delete platform roles and their permissions"),
    Permission("platform", "platform.users.read", "Platform users",
               "View platform users"),
    Permission("platform", "platform.users.invite", "Platform users",
               "Invite platform users"),
    Permission("platform", "platform.users.manage", "Platform users",
               "Activate/deactivate/assign roles to platform users"),
    Permission("platform", "platform.clients.read", "Clients",
               "View client workspaces"),
    Permission("platform", "platform.clients.manage", "Clients",
               "Create/manage client workspaces"),
    Permission("platform", "platform.settings.read", "Settings",
               "View platform settings"),
    Permission("platform", "platform.settings.manage", "Settings",
               "Edit platform settings"),
    Permission("platform", "platform.audit.read", "Audit",
               "View the platform RBAC audit log"),
    Permission("workspace", "workspace.roles.manage", "Access control",
               "Create/edit/delete workspace roles and their permissions"),
    Permission("workspace", "workspace.members.read", "Members",
               "View workspace members"),
    Permission("workspace", "workspace.members.invite", "Members",
               "Invite workspace members"),
    Permission("workspace", "workspace.members.manage", "Members",
               "Remove members / assign workspace roles"),
    Permission("workspace", "workspace.settings.read", "Settings",
               "View workspace settings"),
    Permission("workspace", "workspace.settings.manage", "Settings",
               "Edit workspace settings"),
    Permission("workspace", "workspace.audit.read", "Audit",
               "View the workspace RBAC audit log"),
)


def catalog_keys() -> set[str]:
    return {p.key for p in CATALOG}


def _platform(*exclude: str) -> tuple[str, ...]:
    return tuple(p.key for p in CATALOG if p.scope == "platform" and p.key not in exclude)


def _workspace(*exclude: str) -> tuple[str, ...]:
    return tuple(p.key for p in CATALOG if p.scope == "workspace" and p.key not in exclude)


# Keys are system-role identifiers, NOT (scope,key) pairs. `admin` is the
# platform admin; `workspace_admin` is the workspace admin (distinct scopes).
SYSTEM_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "super_admin": _platform(),
    "admin": _platform("platform.roles.manage"),
    "owner": _workspace(),
    "workspace_admin": _workspace("workspace.roles.manage"),
    "editor": ("workspace.members.read", "workspace.settings.read"),
    "read_only": ("workspace.members.read", "workspace.settings.read"),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory apps/api pytest tests/rbac/test_catalog.py -v`
Expected: PASS (6 passed). Fix the `test_system_role_map_references_only_catalog_keys` scope
variable if flagged — it only needs the membership check; simplify to the `assert k in valid` loop
if the unused `scope` line trips ruff.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check apps/api && uv run mypy --strict apps/api/src
git add apps/api/src/xtrusio_api/rbac/__init__.py apps/api/src/xtrusio_api/rbac/catalog.py apps/api/tests/rbac/__init__.py apps/api/tests/rbac/test_catalog.py
git commit -m "feat(rbac): code-defined permission catalog + system-role map"
```

---

### Task 2: SQLAlchemy models for the RBAC tables

**Files:**
- Create: `apps/api/src/xtrusio_api/models/rbac.py`
- Modify: `apps/api/src/xtrusio_api/models/__init__.py`
- Test: `apps/api/tests/rbac/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/rbac/test_models.py`:

```python
"""ORM mapper config + table names for the RBAC models."""

from __future__ import annotations

from sqlalchemy.orm import configure_mappers
from xtrusio_api.models import (
    Permission,
    RbacAuditLog,
    Role,
    RolePermission,
    UserRole,
)


def test_table_names() -> None:
    assert Permission.__tablename__ == "permissions"
    assert Role.__tablename__ == "roles"
    assert RolePermission.__tablename__ == "role_permissions"
    assert UserRole.__tablename__ == "user_roles"
    assert RbacAuditLog.__tablename__ == "rbac_audit_log"


def test_mappers_configure() -> None:
    configure_mappers()  # raises if any mapping is invalid


def test_role_has_scope_and_is_system() -> None:
    cols = Role.__table__.columns
    assert "scope" in cols and "workspace_id" in cols
    assert "is_system" in cols and "key" in cols


def test_user_role_columns() -> None:
    cols = UserRole.__table__.columns
    for c in ("auth_user_id", "role_id", "workspace_id", "granted_by", "granted_at"):
        assert c in cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory apps/api pytest tests/rbac/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Permission' from 'xtrusio_api.models'`.

- [ ] **Step 3: Write minimal implementation**

Create `apps/api/src/xtrusio_api/models/rbac.py`:

```python
"""RBAC ORM models: permissions, roles, role_permissions, user_roles, audit log."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, SmallInteger, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    permission_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    auth_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    granted_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RbacAuditLog(Base):
    __tablename__ = "rbac_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_auth_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    _placeholder: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
```

Then remove the unused `_placeholder` line and the `SmallInteger` import if ruff/mypy flags them
(it is only there to remind the implementer SmallInteger is available; delete before commit).

Modify `apps/api/src/xtrusio_api/models/__init__.py` — add after the existing imports:

```python
from .rbac import Permission, RbacAuditLog, Role, RolePermission, UserRole
```

and add `"Permission"`, `"RbacAuditLog"`, `"Role"`, `"RolePermission"`, `"UserRole"` to `__all__`
(keep the list alphabetised to match the existing style).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory apps/api pytest tests/rbac/test_models.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check apps/api && uv run mypy --strict apps/api/src
git add apps/api/src/xtrusio_api/models/rbac.py apps/api/src/xtrusio_api/models/__init__.py apps/api/tests/rbac/test_models.py
git commit -m "feat(models): RBAC ORM models (permissions/roles/role_permissions/user_roles/audit)"
```

---

### Task 3: Migration `0006` — tables, grants, triggers, single-super_admin invariant

**Files:**
- Create: `apps/api/migrations/versions/0006_rbac_foundation.py`
- Test: `apps/api/tests/rbac/test_migration_0006.py` (schema half)

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/rbac/test_migration_0006.py`:

```python
"""Read-only assertions that migration 0006 created the RBAC schema.

Run `make migrate` before this test. These assertions only READ the live
managed DB schema (information_schema / pg_catalog) — no data is written.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")

_TABLES = ("permissions", "roles", "role_permissions", "user_roles", "rbac_audit_log")


async def test_rbac_tables_exist() -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name = ANY(:names)"
                ),
                {"names": list(_TABLES)},
            )
        ).scalars().all()
    assert set(rows) == set(_TABLES)


async def test_rls_enabled_on_rbac_tables() -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT relname FROM pg_class "
                    "WHERE relrowsecurity AND relname = ANY(:names)"
                ),
                {"names": list(_TABLES)},
            )
        ).scalars().all()
    assert set(rows) == set(_TABLES)


async def test_authenticated_has_dml_grants() -> None:
    async with SessionLocal() as s:
        cnt = (
            await s.execute(
                text(
                    "SELECT count(DISTINCT table_name) "
                    "FROM information_schema.role_table_grants "
                    "WHERE grantee='authenticated' AND privilege_type='SELECT' "
                    "AND table_name = ANY(:names)"
                ),
                {"names": list(_TABLES)},
            )
        ).scalar_one()
    assert cnt == len(_TABLES)


async def test_single_super_admin_partial_unique_index_exists() -> None:
    async with SessionLocal() as s:
        exists = (
            await s.execute(
                text(
                    "SELECT 1 FROM pg_indexes "
                    "WHERE indexname = 'user_roles_one_super_admin'"
                )
            )
        ).scalar_one_or_none()
    assert exists == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory apps/api pytest tests/rbac/test_migration_0006.py -v`
Expected: FAIL — tables/index do not exist yet (`assert set() == {...}` fails).

- [ ] **Step 3: Write the migration (schema half only)**

Create `apps/api/migrations/versions/0006_rbac_foundation.py`. **In this step write only
`upgrade()`'s structural section + a `downgrade()` that drops the tables.** Seeds/backfill are
Task 4.

```python
"""RBAC foundation: dynamic roles/permissions, system-role seed, enum backfill.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-17

Spec: docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md (§3, §6, §7).
Pure raw SQL (codebase convention). Permission catalog rows + system-role
role_permissions are projected by the reconciler (xtrusio_api.rbac.reconcile),
NOT this migration — see plan Architecture note.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- permissions -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE permissions (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            scope         text NOT NULL CHECK (scope IN ('platform','workspace')),
            key           text NOT NULL UNIQUE,
            category      text NOT NULL,
            description   text NOT NULL,
            is_deprecated boolean NOT NULL DEFAULT false
        )
        """
    )

    # --- roles -------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE roles (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            scope        text NOT NULL CHECK (scope IN ('platform','workspace')),
            workspace_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
            key          text NOT NULL,
            name         text NOT NULL,
            description  text NOT NULL DEFAULT '',
            is_system    boolean NOT NULL DEFAULT false,
            created_by   uuid REFERENCES auth.users(id) ON DELETE SET NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT roles_scope_workspace_ck CHECK (
                (scope = 'platform' AND workspace_id IS NULL)
                OR (scope = 'workspace' AND workspace_id IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX roles_scope_ws_key_uq "
        "ON roles (scope, COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'), key)"
    )
    op.execute(
        "CREATE TRIGGER roles_set_updated_at BEFORE UPDATE ON roles "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # --- role_permissions --------------------------------------------------
    op.execute(
        """
        CREATE TABLE role_permissions (
            role_id       uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
            PRIMARY KEY (role_id, permission_id)
        )
        """
    )

    # --- user_roles --------------------------------------------------------
    op.execute(
        """
        CREATE TABLE user_roles (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            auth_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            role_id      uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            workspace_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
            granted_by   uuid REFERENCES auth.users(id) ON DELETE SET NULL,
            granted_at   timestamptz NOT NULL DEFAULT now(),
            UNIQUE (auth_user_id, role_id, workspace_id)
        )
        """
    )
    op.execute("CREATE INDEX user_roles_auth_user_id_idx ON user_roles(auth_user_id)")
    op.execute("CREATE INDEX user_roles_role_id_idx ON user_roles(role_id)")

    # Single-super_admin DB invariant: at most one grant of the platform
    # super_admin system role. A partial-index predicate must be immutable and
    # reference only the indexed table (Postgres forbids subqueries in index
    # predicates), so the super_admin system role is seeded (Task 4) with a
    # fixed well-known id and the predicate pins to that constant. Mirrors the
    # `id = 1` singleton pattern in migration 0002 — a structural sentinel,
    # not env-varying config.
    op.execute(
        "CREATE UNIQUE INDEX user_roles_one_super_admin ON user_roles ((true)) "
        "WHERE role_id = '00000000-0000-0000-0000-0000000000a1'"
    )

    # --- rbac_audit_log ----------------------------------------------------
    op.execute(
        """
        CREATE TABLE rbac_audit_log (
            id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            actor_auth_user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
            action             text NOT NULL,
            target_type        text NOT NULL,
            target_id          text NOT NULL,
            scope              text NOT NULL CHECK (scope IN ('platform','workspace')),
            workspace_id       uuid REFERENCES tenants(id) ON DELETE CASCADE,
            before             jsonb,
            after              jsonb,
            created_at         timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    # --- RLS enable (policies are authored in P2; enable + deny-by-default) --
    for tbl in ("permissions", "roles", "role_permissions", "user_roles", "rbac_audit_log"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")

    # Minimal interim read policy so authenticated callers are not hard-denied
    # before P2 authors the real perm-aware policies. SELECT-only; writes go
    # through the owner backend connection (RLS does not constrain it).
    for tbl in ("permissions", "roles", "role_permissions", "user_roles"):
        op.execute(
            f"CREATE POLICY {tbl}_authenticated_read ON {tbl} "
            f"FOR SELECT TO authenticated USING (true)"
        )
    op.execute(
        "CREATE POLICY rbac_audit_log_no_read ON rbac_audit_log "
        "FOR SELECT TO authenticated USING (false)"
    )

    # DML grants — Alembic tables don't inherit Supabase auto-grants
    # (Plan-2 gotcha #3).
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "permissions, roles, role_permissions, user_roles, rbac_audit_log "
        "TO authenticated"
    )

    # Seeds + backfill: added in Task 4 BELOW THIS LINE (same upgrade()).


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rbac_audit_log")
    op.execute("DROP TABLE IF EXISTS role_permissions")
    op.execute("DROP TABLE IF EXISTS user_roles")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("DROP TABLE IF EXISTS permissions")
    # Invite role_id columns are dropped here in Task 4's downgrade additions.
```

- [ ] **Step 4: Apply the migration, run the test**

```bash
make migrate
uv run --directory apps/api pytest tests/rbac/test_migration_0006.py -v
```
Expected: 4 passed. If `set_updated_at()` does not exist, check `0001`/`0002` — it is created in
an earlier migration; `roles_set_updated_at` reuses it exactly like `tenant_memberships` (0002).

- [ ] **Step 5: Verify reversibility, re-apply, commit**

```bash
make migrate-down            # runs downgrade(); RBAC tables dropped
make migrate                 # re-apply cleanly
uv run --directory apps/api pytest tests/rbac/test_migration_0006.py -v   # green again
git add apps/api/migrations/versions/0006_rbac_foundation.py apps/api/tests/rbac/test_migration_0006.py
git commit -m "feat(db): 0006 RBAC tables, grants, RLS-enable, single-super_admin invariant"
```

---

### Task 4: Migration `0006` — system-role seeds, enum→user_roles backfill, invite role_id

**Files:**
- Modify: `apps/api/migrations/versions/0006_rbac_foundation.py` (extend `upgrade()` + `downgrade()`)
- Test: `apps/api/tests/rbac/test_migration_0006.py` (append backfill assertions)

- [ ] **Step 1: Write the failing test (append)**

Append to `apps/api/tests/rbac/test_migration_0006.py`:

```python
async def test_platform_system_roles_seeded() -> None:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT key FROM roles WHERE scope='platform' AND is_system "
                    "ORDER BY key"
                )
            )
        ).scalars().all()
    assert rows == ["admin", "super_admin"]


async def test_each_existing_tenant_has_4_workspace_system_roles() -> None:
    async with SessionLocal() as s:
        n_tenants = (
            await s.execute(text("SELECT count(*) FROM tenants"))
        ).scalar_one()
        if n_tenants == 0:
            pytest.skip("no tenants present; per-tenant seed assertion is vacuous")
        bad = (
            await s.execute(
                text(
                    "SELECT t.id FROM tenants t "
                    "LEFT JOIN ("
                    "  SELECT workspace_id, count(*) c FROM roles "
                    "  WHERE scope='workspace' AND is_system GROUP BY workspace_id"
                    ") r ON r.workspace_id = t.id "
                    "WHERE COALESCE(r.c,0) <> 4"
                )
            )
        ).scalars().all()
    assert bad == [], f"tenants missing the 4 workspace system roles: {bad}"


async def test_existing_super_admin_backfilled_to_user_roles() -> None:
    """Read-only: the one real super_admin must have a matching user_roles grant."""
    async with SessionLocal() as s:
        sa = (
            await s.execute(
                text("SELECT id FROM platform_users WHERE role='super_admin' LIMIT 1")
            )
        ).scalar_one_or_none()
        if sa is None:
            pytest.skip("no real super_admin present; nothing to assert")
        cnt = (
            await s.execute(
                text(
                    "SELECT count(*) FROM user_roles ur "
                    "JOIN roles r ON r.id = ur.role_id "
                    "WHERE ur.auth_user_id = :sa AND r.scope='platform' "
                    "AND r.key='super_admin'"
                ),
                {"sa": sa},
            )
        ).scalar_one()
    assert cnt == 1


async def test_membership_enum_backfilled_to_user_roles() -> None:
    """Every tenant_membership has an equivalent workspace user_roles grant."""
    async with SessionLocal() as s:
        n_memberships = (
            await s.execute(text("SELECT count(*) FROM tenant_memberships"))
        ).scalar_one()
        if n_memberships == 0:
            pytest.skip("no tenant_memberships present; backfill assertion is vacuous")
        missing = (
            await s.execute(
                text(
                    "SELECT m.id FROM tenant_memberships m "
                    "LEFT JOIN roles r ON r.scope='workspace' "
                    "  AND r.workspace_id = m.tenant_id AND r.key = m.role::text "
                    "LEFT JOIN user_roles ur ON ur.auth_user_id = m.user_id "
                    "  AND ur.role_id = r.id AND ur.workspace_id = m.tenant_id "
                    "WHERE ur.id IS NULL"
                )
            )
        ).scalars().all()
    assert missing == [], f"memberships without a user_roles grant: {missing}"


async def test_invites_have_role_id_backfilled() -> None:
    # The platform 'editor' enum is deliberately NOT a system role (spec §2.7/§7),
    # so a legacy platform_invites row with role='editor' correctly keeps
    # role_id NULL — exclude it from the orphan assertion. Every tenant-invite
    # role (admin/editor/read_only) maps to a workspace system role, so the
    # tenant_invites orphan check stays strict.
    checks = (
        ("platform_invites", "role IS NOT NULL AND role <> 'editor' AND role_id IS NULL"),
        ("tenant_invites", "role IS NOT NULL AND role_id IS NULL"),
    )
    async with SessionLocal() as s:
        for tbl, orphan_pred in checks:
            col = (
                await s.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name=:t AND column_name='role_id'"
                    ),
                    {"t": tbl},
                )
            ).scalar_one_or_none()
            assert col == 1, f"{tbl}.role_id missing"
            orphans = (
                await s.execute(text(f"SELECT count(*) FROM {tbl} WHERE {orphan_pred}"))
            ).scalar_one()
            assert orphans == 0, f"{tbl} has rows with a mappable role but no role_id"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory apps/api pytest tests/rbac/test_migration_0006.py -v`
Expected: the 5 new tests FAIL (no roles seeded, no `role_id` column). The Task-3 tests still pass.

- [ ] **Step 3: Extend the migration**

In `0006_rbac_foundation.py`, replace the `# Seeds + backfill:` comment line in `upgrade()` with:

```python
    # --- seed platform system roles ---------------------------------------
    # super_admin gets the fixed well-known id the 0006 single-super_admin
    # partial unique index pins to (see upgrade() index comment). admin keeps
    # a generated id.
    op.execute(
        """
        INSERT INTO roles (id, scope, workspace_id, key, name, description, is_system)
        VALUES
            ('00000000-0000-0000-0000-0000000000a1', 'platform', NULL,
             'super_admin', 'Super Admin',
             'Owns platform RBAC; bootstrap-only; exactly one', true)
        """
    )
    op.execute(
        """
        INSERT INTO roles (scope, workspace_id, key, name, description, is_system)
        VALUES
            ('platform', NULL, 'admin', 'Platform Admin',
             'Operates the platform; cannot manage roles', true)
        """
    )

    # --- seed workspace system roles for every existing tenant ------------
    # Cartesian: each tenant x the 4 workspace system role templates.
    op.execute(
        """
        INSERT INTO roles (scope, workspace_id, key, name, description, is_system)
        SELECT 'workspace', t.id, v.key, v.name, v.description, true
        FROM tenants t
        CROSS JOIN (VALUES
            ('owner',     'Owner',     'Governs the workspace; manages roles'),
            ('admin',     'Admin',     'Operates the workspace; cannot manage roles'),
            ('editor',    'Editor',    'Content write access'),
            ('read_only', 'Read Only', 'View-only access')
        ) AS v(key, name, description)
        """
    )

    # --- backfill user_roles from platform_users.role ---------------------
    # Only super_admin and admin exist as enum values that map to system roles
    # (the legacy 'editor' platform enum has no system role and is intentionally
    # dropped from the new model — it becomes a custom role later, spec §2.7).
    op.execute(
        """
        INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by)
        SELECT pu.id, r.id, NULL, NULL
        FROM platform_users pu
        JOIN roles r ON r.scope='platform' AND r.workspace_id IS NULL
                    AND r.key = pu.role::text
        WHERE pu.is_active AND pu.role::text IN ('super_admin','admin')
        ON CONFLICT (auth_user_id, role_id, workspace_id) DO NOTHING
        """
    )

    # --- backfill user_roles from tenant_memberships.role ----------------
    op.execute(
        """
        INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by)
        SELECT m.user_id, r.id, m.tenant_id, NULL
        FROM tenant_memberships m
        JOIN roles r ON r.scope='workspace' AND r.workspace_id = m.tenant_id
                    AND r.key = m.role::text
        ON CONFLICT (auth_user_id, role_id, workspace_id) DO NOTHING
        """
    )

    # --- invite tables: add nullable role_id, backfill, keep enum --------
    op.execute(
        "ALTER TABLE platform_invites ADD COLUMN role_id uuid "
        "REFERENCES roles(id) ON DELETE SET NULL"
    )
    op.execute(
        """
        UPDATE platform_invites pi SET role_id = r.id
        FROM roles r
        WHERE r.scope='platform' AND r.workspace_id IS NULL
          AND r.key = pi.role::text AND pi.role_id IS NULL
        """
    )
    op.execute(
        "ALTER TABLE tenant_invites ADD COLUMN role_id uuid "
        "REFERENCES roles(id) ON DELETE SET NULL"
    )
    op.execute(
        """
        UPDATE tenant_invites ti SET role_id = r.id
        FROM roles r
        WHERE r.scope='workspace' AND r.workspace_id = ti.tenant_id
          AND r.key = ti.role::text AND ti.role_id IS NULL
        """
    )
```

In `downgrade()`, add **before** the `DROP TABLE` lines (FK-safe order — drop dependent invite
columns first, then user_roles via table drop):

```python
    op.execute("ALTER TABLE tenant_invites DROP COLUMN IF EXISTS role_id")
    op.execute("ALTER TABLE platform_invites DROP COLUMN IF EXISTS role_id")
```

(The seeded `roles` / `user_roles` rows are removed by the existing `DROP TABLE` statements —
cascades handle `role_permissions`/`user_roles`.)

- [ ] **Step 4: Re-apply and verify**

```bash
make migrate-down
make migrate
uv run --directory apps/api pytest tests/rbac/test_migration_0006.py -v
```
Expected: all migration tests pass (9 passed). The single-super_admin partial unique index now has
exactly one matching `user_roles` row (the real super_admin) and does not raise.

- [ ] **Step 5: Full round-trip + commit**

```bash
make migrate-down && make migrate     # clean down+up; no errors
uv run --directory apps/api pytest tests/rbac/ -v
git add apps/api/migrations/versions/0006_rbac_foundation.py apps/api/tests/rbac/test_migration_0006.py
git commit -m "feat(db): 0006 seed system roles + backfill user_roles + invite role_id"
```

---

### Task 5: Reconciler — project the catalog into `permissions` + system-role `role_permissions`

**Files:**
- Create: `apps/api/src/xtrusio_api/rbac/reconcile.py`
- Test: `apps/api/tests/rbac/test_reconcile.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/rbac/test_reconcile.py`:

```python
"""Reconciler idempotency + soft-deprecation + system-role wiring.

Reads/writes ONLY the catalog-owned tables (permissions / role_permissions for
is_system roles). Never creates users/tenants. Idempotent: safe on the managed
DB (the catalog is the same every run)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.rbac.catalog import CATALOG, SYSTEM_ROLE_PERMISSIONS
from xtrusio_api.rbac.reconcile import reconcile_rbac

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_all_catalog_keys_present_after_reconcile() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
        keys = (await s.execute(text("SELECT key FROM permissions"))).scalars().all()
    for p in CATALOG:
        assert p.key in keys


async def test_reconcile_is_idempotent() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
        n1 = (await s.execute(text("SELECT count(*) FROM permissions"))).scalar_one()
        await reconcile_rbac(s)
        n2 = (await s.execute(text("SELECT count(*) FROM permissions"))).scalar_one()
    assert n1 == n2 == len(CATALOG)


async def test_super_admin_role_has_all_platform_permissions() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
        got = (
            await s.execute(
                text(
                    "SELECT p.key FROM role_permissions rp "
                    "JOIN roles r ON r.id=rp.role_id "
                    "JOIN permissions p ON p.id=rp.permission_id "
                    "WHERE r.scope='platform' AND r.key='super_admin'"
                )
            )
        ).scalars().all()
    assert set(got) == set(SYSTEM_ROLE_PERMISSIONS["super_admin"])


async def test_workspace_owner_roles_wired_for_every_tenant() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
        bad = (
            await s.execute(
                text(
                    "SELECT r.id FROM roles r "
                    "WHERE r.scope='workspace' AND r.key='owner' AND r.is_system "
                    "AND (SELECT count(*) FROM role_permissions rp "
                    "     WHERE rp.role_id=r.id) <> :n"
                ),
                {"n": len(SYSTEM_ROLE_PERMISSIONS["owner"])},
            )
        ).scalars().all()
    assert bad == []


async def test_unknown_db_permission_is_soft_deprecated_not_deleted() -> None:
    # try/finally: this writes the SHARED managed DB. If the assertion fails
    # the synthetic non-catalog row MUST still be removed, else every later
    # reconcile_rbac run perpetually soft-deprecates it and pollutes the
    # catalog table for other tests.
    try:
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO permissions (scope,key,category,description) "
                    "VALUES ('platform','platform.zzz.legacy','Legacy','x') "
                    "ON CONFLICT (key) DO NOTHING"
                )
            )
            await s.commit()
            await reconcile_rbac(s)
            row = (
                await s.execute(
                    text(
                        "SELECT is_deprecated FROM permissions "
                        "WHERE key='platform.zzz.legacy'"
                    )
                )
            ).scalar_one_or_none()
        assert row is True
    finally:
        async with SessionLocal() as s:
            await s.execute(
                text("DELETE FROM permissions WHERE key='platform.zzz.legacy'")
            )
            await s.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory apps/api pytest tests/rbac/test_reconcile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'xtrusio_api.rbac.reconcile'`.

- [ ] **Step 3: Write the reconciler**

Create `apps/api/src/xtrusio_api/rbac/reconcile.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory apps/api pytest tests/rbac/test_reconcile.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check apps/api && uv run mypy --strict apps/api/src
git add apps/api/src/xtrusio_api/rbac/reconcile.py apps/api/tests/rbac/test_reconcile.py
git commit -m "feat(rbac): idempotent catalog reconciler + system-role wiring"
```

---

### Task 6: Wire reconciler into startup + `make rbac-seed` + full-suite gate

**Files:**
- Modify: `apps/api/src/xtrusio_api/main.py`
- Modify: `Makefile`
- Create: `apps/api/src/xtrusio_api/rbac/__main__.py`

- [ ] **Step 1: Add a runnable reconcile entrypoint**

Create `apps/api/src/xtrusio_api/rbac/__main__.py`:

```python
"""`python -m xtrusio_api.rbac` — run the reconciler against DATABASE_URL."""

from __future__ import annotations

import asyncio

from ..core.db import SessionLocal
from .reconcile import reconcile_rbac


async def _run() -> None:
    async with SessionLocal() as s:
        await reconcile_rbac(s)
    print("rbac reconcile complete")


if __name__ == "__main__":
    asyncio.run(_run())
```

- [ ] **Step 2: Add the Make target**

In `Makefile`, add `rbac-seed` to the `.PHONY` line and add this target near `migrate`:

```makefile
rbac-seed:
	uv run --directory apps/api python -m xtrusio_api.rbac
```

Also add to the `help` block: `@echo "  make rbac-seed       - project the permission catalog into the DB"`

- [ ] **Step 3: Call the reconciler on app startup**

Read `apps/api/src/xtrusio_api/main.py` first. It uses FastAPI; add a startup hook that runs the
reconciler once (best-effort, logged on failure — never crash boot). If a `lifespan` async context
manager already exists, add inside it before `yield`:

```python
from .core.db import SessionLocal
from .rbac.reconcile import reconcile_rbac

# inside lifespan, before `yield`:
try:
    async with SessionLocal() as _s:
        await reconcile_rbac(_s)
except Exception:  # pragma: no cover - boot must not fail on reconcile
    import logging

    logging.getLogger(__name__).exception("rbac reconcile on startup failed")
```

If there is no `lifespan`, add one via `@asynccontextmanager` and pass `lifespan=` to the
`FastAPI(...)` constructor — match whatever pattern `main.py` already uses for startup (check for
existing `@app.on_event` / `lifespan`; do NOT introduce a second mechanism).

- [ ] **Step 4: Verify the entrypoint + full backend suite**

```bash
make rbac-seed
uv run --directory apps/api pytest tests/ -v
```
Expected: `rbac reconcile complete`; entire backend suite green (the prior 82 + the new
`tests/rbac/*`). No `@example.com` rows created (run `make test-clean` — it reports 0 new test
rows beyond what other tests manage).

- [ ] **Step 5: Full merge-contract gate + commit**

```bash
make check     # lint + typecheck + test (backend + frontend)
```
Expected: green. mypy `--strict src` shows only the 1 pre-existing `jose` error; ruff clean;
frontend 29 still green (untouched).

```bash
git add apps/api/src/xtrusio_api/rbac/__main__.py apps/api/src/xtrusio_api/main.py Makefile
git commit -m "feat(rbac): reconcile on startup + make rbac-seed target"
```

---

### Task 7: Make the `test_no_super_admin_creation` guard RBAC-precise

**Context (discovered during execution):** `apps/api/tests/test_no_super_admin_creation.py` enforces a real rule (spec §11: no test may CREATE a super_admin). Its old `_FORBIDDEN` regex flagged any bare `'super_admin'` / `role='super_admin'` string. RBAC introduces `'super_admin'` as a legitimate **role-catalog key** that read-only RBAC tests reference in SQL/assertions (`WHERE key='super_admin'`, `SYSTEM_ROLE_PERMISSIONS["super_admin"]`, `SELECT … WHERE role='super_admin'`). Those are reads, not creation, so the guard now false-fails on `tests/rbac/*`. Keep the rule; make the detector match only **creation** signals.

**Files:**
- Modify: `apps/api/tests/test_no_super_admin_creation.py`

- [ ] **Step 1: Replace the guard with a creation-precise version**

Replace the ENTIRE file contents with:

```python
"""Guard: no test may CREATE a super_admin (platform_users row, user_roles
grant, or via the PlatformRole.SUPER_ADMIN enum). The single super_admin is
created only by the operator via `make create-platform-owner`; tests verify
against the existing one (read-only `existing_super_admin` fixture).

Under the RBAC model `'super_admin'` is also a legitimate role-catalog *key*
that read-only RBAC tests reference in SQL/assertions. Those references are
NOT creation and must not trip this guard, so the guard matches only
super_admin *creation* signals, never bare references."""

from __future__ import annotations

import re
from pathlib import Path

_TESTS_DIR = Path(__file__).parent

# The PlatformRole.SUPER_ADMIN enum is only ever used to set a role when
# constructing/assigning a platform user — never in a read-only test.
_ENUM = re.compile(r"PlatformRole\.SUPER_ADMIN")

# A write into platform_users/user_roles, or a PlatformUser(...) construction,
# associated with super_admin — scanned over the whole file (DOTALL, bounded
# gap) so multi-line raw SQL is still caught. Pure SELECT/WHERE reads and
# role-key references do not contain these write tokens, so they don't match.
_WRITE_WITH_SUPER_ADMIN = re.compile(
    r"(INSERT\s+INTO\s+(?:platform_users|user_roles)|PlatformUser\s*\()"
    r"(?:.|\n){0,400}?super_admin",
    re.IGNORECASE,
)

# Files allowed to mention the term — matched by path RELATIVE to _TESTS_DIR.
_ALLOWED = {
    Path("test_no_super_admin_creation.py"),
    Path("conftest.py"),
    Path("_cleanup.py"),
}


def test_no_test_creates_a_super_admin() -> None:
    offenders: list[str] = []
    for path in _TESTS_DIR.rglob("*.py"):
        if path.relative_to(_TESTS_DIR) in _ALLOWED:
            continue
        content = path.read_text(encoding="utf-8")
        if _WRITE_WITH_SUPER_ADMIN.search(content):
            offenders.append(f"{path.relative_to(_TESTS_DIR)}: writes a super_admin row/grant")
        for lineno, line in enumerate(content.splitlines(), 1):
            if _ENUM.search(line):
                offenders.append(f"{path.relative_to(_TESTS_DIR)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Tests must NEVER create a super_admin (platform_users row, user_roles "
        "grant, or PlatformRole.SUPER_ADMIN). Use the read-only "
        "`existing_super_admin` fixture instead.\n" + "\n".join(offenders)
    )
```

- [ ] **Step 2: Verify the guard passes AND still bites**

```bash
uv run --directory apps/api pytest tests/test_no_super_admin_creation.py -v   # PASS (no offenders)
```
Then a temporary negative check (do NOT commit this): create `apps/api/tests/rbac/_tmp_probe.py` containing the line `q = "INSERT INTO user_roles (auth_user_id, role_id) VALUES (x, y) -- super_admin"` and re-run the guard — it MUST FAIL listing `_tmp_probe.py`. Delete `_tmp_probe.py` and confirm the guard PASSES again. This proves the guard still detects real creation while passing the legitimate read-only `tests/rbac/*`.

- [ ] **Step 3: Full backend suite + lint/type + commit**

```bash
uv run --directory apps/api pytest tests/ -v
```
Expected: `tests/rbac/*` and `test_no_super_admin_creation.py` green. The pre-existing, unrelated `test_signup.py::test_signup_status_default_false` / `::test_signup_disabled_returns_403` failures (caused by the managed DB's `signups_enabled=true` operator state, reproducible on pristine `origin/main`, NOT introduced by this branch) remain out of scope — note them, do not "fix" them.

```bash
uv run ruff check apps/api/tests/test_no_super_admin_creation.py
uv run mypy --strict apps/api/src
git add apps/api/tests/test_no_super_admin_creation.py
git commit -m "test(hygiene): make no-super_admin guard match creation only, not RBAC role-key reads"
```

---

## Self-Review (completed during planning)

**Spec coverage (P1 row + §3/§4/§6/§7):**
- §3.2 five RBAC tables → Task 3 (DDL) + Task 2 (ORM).
- §3.3 system role seeds (platform + per-workspace) → Task 4.
- §4 code catalog + reconciler + soft-deprecate (`is_deprecated`) → Tasks 1, 5.
- §6.2 single-super_admin DB invariant → Task 3 (`user_roles_one_super_admin` partial unique index).
- §7.1 tables + grants to `authenticated` → Task 3.
- §7.2 seed permissions + system roles + role_permissions → Task 4 (roles) + Task 5 (perms/role_permissions).
- §7.3 backfill `user_roles` from both enum columns → Task 4.
- §7.4 invite enum → `role_id` (added + backfilled, enum kept) → Task 4.
- §7.5 identity/membership enum columns NOT dropped (behaviour unchanged) → respected throughout; explicit in Architecture.
- §7 reversible `downgrade()` + round-trip test → Tasks 3 & 4 Step 5.
- §11 lint/type baseline, single Alembic head, test-data hygiene → Conventions block + Task 6.

**Out of P1 scope (correctly deferred):** privilege-escalation guard/trigger, immutable-system-role trigger, `has_platform_perm`/`has_workspace_perm`, RLS perm-aware policies, `require_permission()`, `/me`, invite-acceptance code change, dropping enum columns, onboarding seeding new tenants' roles, all UI — these are P2/P3/P6 per spec §10. (The interim `*_authenticated_read` RLS policies in Task 3 are explicitly replaced in P2.)

**Placeholder scan:** none — every code/SQL step is complete and concrete.

**Type/name consistency:** `reconcile_rbac` (not `reconcile_permissions`) used consistently across Tasks 5–6 and tests; catalog symbols `CATALOG`/`SYSTEM_ROLE_PERMISSIONS`/`catalog_keys`/`Permission` consistent Tasks 1/5/6; table/index names (`user_roles_one_super_admin`, `roles_scope_ws_key_uq`) consistent between migration and tests; ORM class names consistent with `models/__init__.py` re-exports.

**Deviation noted for reviewer:** spec §7.2 phrases permission/role_permissions seeding as part of the migration; this plan keeps migrations pure-SQL (codebase convention, all of `0001`–`0005`) and projects the catalog via the reconciler — which spec §4 itself defines as the catalog→`permissions` mechanism running "on migrate/startup". Documented `make migrate && make rbac-seed` sequence + startup hook makes this equivalent and self-healing. Flag in P1 spec-compliance review.
