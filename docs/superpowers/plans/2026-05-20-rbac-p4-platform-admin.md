# P4 — Platform RBAC Admin (API + Governance) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the platform-side of the RBAC admin surface — `super_admin` can CRUD custom platform roles, attach catalog permissions to them, grant/revoke role assignments on platform users, and view a paginated audit log. Bundles the deferred-from-P3c governance: audit-log writes on every RBAC mutation, privilege-escalation guard (service + DB trigger), single-super_admin service-layer check, immutable system roles (DB trigger). Backend only — UI deferred to P6c.

**Architecture:** Four slices, one PR. **(A)** Migration `0009` adds DB triggers + new audit-write helper module → **(B)** platform-role CRUD service + REST endpoints → **(C)** role-assignment endpoints + service-layer privilege-escalation & single-super_admin guards → **(D)** audit-log viewer endpoint (cursor-paginated). Reuses `0007` resolvers, `require_permission` (P3b), `grant_role` (P3a), `core/pagination.py` (P3.5). No frontend changes.

**Tech Stack:** Same as the rest of the API — FastAPI, SQLAlchemy async, pydantic v2, Alembic, `mypy --strict`, ruff. New DB triggers in plain PL/pgSQL inside the Alembic migration. Audit-log writes happen in the same DB transaction as the mutation they record (atomic).

---

## Prerequisite

This plan **assumes the [Type-the-Tests plan](./2026-05-20-type-the-tests.md) has been merged first** so the end-of-slice `make check` gate goes green. If type-the-tests is not yet merged, P4 still works locally, but `make check` will inherit ~49 pre-existing mypy errors that aren't from this PR.

---

## Execution-model constraints

- `feedback_lean_review_workflow`: ONE end-of-slice `make check` by the controller; ONE final Opus code-quality review; ONE PR.
- `feedback_model_selection`: code subagents = Opus; Sonnet only for read-only exploration.
- `feedback_no_claude_coauthor`: no `Co-Authored-By: Claude` trailer.
- `feedback_test_data_hygiene`: `@example.com` emails only; never create a real `super_admin`; use `existing_super_admin` for super-admin behaviour. Custom-role rows can use any non-system key, but seeded test data must be purgeable via `_cleanup.py` (audit-log rows pointing at `@example.com` actors will be cleaned by extending `_cleanup.py` to cover `rbac_audit_log` — see Task A2).
- `feedback_no_hardcoded_config`: no env-varying value as a literal anywhere in code or workflows.
- HANDOFF execution: end with `docs/superpowers/PR-rbac-p4-body.md`, `gh pr create`, `gh pr merge`, verify `gh pr view <n> --json state` = MERGED, then update HANDOFF.md and clean the branch.

---

## Spec anchors

- `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` §4 (permission catalog), §6 (governance), §3.2 (tables — `roles / role_permissions / user_roles / rbac_audit_log / permissions`).
- HANDOFF.md item 1 (P4 scope) and item 3 (governance bundle).

## Permission gates

All P4 endpoints require `super_admin`-level access via the existing `require_permission(db, user_id, "<key>")` (P3b). Specifically:

| Endpoint | Gate |
|---|---|
| Role CRUD (create/list/get/edit/delete) | `platform.roles.manage` |
| Role grant/revoke on platform users | `platform.users.manage` |
| Audit-log viewer | `platform.audit.read` |

All three keys already exist in `apps/api/src/xtrusio_api/rbac/catalog.py` (lines 26, 32, 42). No catalog changes needed.

## Reused primitives

- `xtrusio_api.rbac.grants.grant_role` — idempotent grant of a SYSTEM role (P3a). P4's role-grant service WILL handle **custom** roles too, so it implements its own grant path resolving `roles WHERE id = :role_id AND scope = 'platform'` (no `is_system` requirement). Document why: `grant_role` is for system-role mapping at bootstrap/invite-acceptance time; arbitrary-role grants flow through P4's new service.
- `xtrusio_api.core.permissions.require_permission` — backend authz primitive (P3b).
- `xtrusio_api.core.pagination.{CursorParams, encode_cursor, DEFAULT_LIMIT, MAX_LIMIT}` — list endpoints (P3.5).
- `xtrusio_api.rbac.reconcile.reconcile_rbac` — catalog reconciler runs at boot AND `make rbac-seed`.

---

## File structure

**Created**

| Path | Purpose |
|---|---|
| `apps/api/migrations/versions/0009_rbac_governance_triggers.py` | DB triggers: privilege-escalation, immutable system roles. Reversible. |
| `apps/api/src/xtrusio_api/core/audit.py` | `write_audit_event(db, *, actor_id, action, target_type, target_id, scope, workspace_id, before, after)` — one place writes `rbac_audit_log`. |
| `apps/api/src/xtrusio_api/services/platform_roles.py` | Custom platform-role CRUD: create, list, get, update (name/description/permission set), delete. Enforces immutable-system-roles at service layer. |
| `apps/api/src/xtrusio_api/services/platform_role_grants.py` | Grant/revoke a role to a platform user. Enforces privilege-escalation guard + single-super_admin invariant at service layer. |
| `apps/api/src/xtrusio_api/services/platform_audit_log.py` | Paginated read of `rbac_audit_log` rows where `scope = 'platform'`. |
| `apps/api/src/xtrusio_api/schemas/platform_role.py` | Pydantic schemas: `PlatformRoleIn`, `PlatformRoleOut`, `PlatformRolePatch`, `PlatformRolesPage`, `PlatformRoleGrantOut`, `PlatformRoleGrantsPage`. |
| `apps/api/src/xtrusio_api/schemas/audit_log.py` | `AuditEventOut`, `AuditEventsPage`. |
| `apps/api/src/xtrusio_api/routes/platform_roles.py` | `GET/POST /api/platform/roles`, `GET/PATCH/DELETE /api/platform/roles/{role_id}`, `POST/DELETE /api/platform/users/{user_id}/roles[/{role_id}]`. |
| `apps/api/src/xtrusio_api/routes/platform_audit_log.py` | `GET /api/platform/audit-log`. |
| `apps/api/src/xtrusio_api/models/audit_log.py` | SQLAlchemy ORM model for `rbac_audit_log`. (The table exists since P1; we add the model to enable typed queries.) |
| `apps/api/src/xtrusio_api/models/role.py` | SQLAlchemy ORM models for `roles`, `role_permissions`, `permissions` if not already present. (P1 may have created basic models — read first; add only what's missing.) |
| `apps/api/tests/migrations/test_0009_triggers.py` | DB-level tests for the two triggers (privilege escalation + immutable system roles). |
| `apps/api/tests/services/test_platform_roles.py` | Service-level happy paths + edge cases for role CRUD. |
| `apps/api/tests/services/test_platform_role_grants.py` | Service-level: grant, revoke, privilege escalation rejected, single super_admin invariant. |
| `apps/api/tests/services/test_platform_audit_log.py` | Service-level: paginated read returns platform-scope only. |
| `apps/api/tests/routes/test_platform_roles.py` | Route-level: auth gates (403 without permission), happy paths, validation errors, 404s, 409 on duplicate role key, 422 on system-role mutation attempt. |
| `apps/api/tests/routes/test_platform_audit_log.py` | Route-level: 403 without `platform.audit.read`, pagination round-trip, cursor 400. |
| `apps/api/tests/core/test_audit.py` | Unit tests for `write_audit_event` (correct columns, atomic with caller's tx). |
| `docs/superpowers/PR-rbac-p4-body.md` | PR description at submit time. |

**Modified**

| Path | Change |
|---|---|
| `apps/api/src/xtrusio_api/main.py` | Wire two new routers (`platform_roles_routes`, `platform_audit_log_routes`). |
| `apps/api/tests/_cleanup.py` | Add `rbac_audit_log` purge + custom-role purge to the FK-safe delete order. |

**NOT touched**
- `apps/api/src/xtrusio_api/rbac/catalog.py` — no new permission keys needed.
- `apps/api/src/xtrusio_api/rbac/grants.py` — kept exactly as-is (system-role bootstrap path).
- Migrations `0006`, `0007`, `0008` — already define the tables and resolvers.
- Frontend — entirely out of scope (deferred to P6c).
- Workspace RBAC admin — P5.

---

## Slice A — Foundation (migration + audit writer)

Goal: DB triggers in place; audit-write helper available. Nothing else changes in this slice.

### Task A1: Migration `0009` — privilege-escalation + immutable-system-roles triggers

**Files:**
- Create: `apps/api/migrations/versions/0009_rbac_governance_triggers.py`
- Test: `apps/api/tests/migrations/test_0009_triggers.py`

- [ ] **Step 1: Write the failing test first**

Create `apps/api/tests/migrations/test_0009_triggers.py`:

```python
"""DB-level triggers added in migration 0009.

These tests exercise the triggers directly via raw SQL so the assertions are
independent of any service-layer guard. The service-layer guards (Task C2) are
defense-in-depth — these triggers are the floor.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_priv_escalation_trigger_rejects_grant_of_unheld_perm(
    db_session: AsyncSession,
) -> None:
    """If actor lacks any perm of the target role, INSERT into user_roles raises."""
    # Setup: create two @example.com auth users; user_a holds an empty role (no perms);
    # user_b holds super_admin (every perm). Try to INSERT user_roles where user_a
    # grants the platform 'admin' role to a third user. Expect raise.
    # ... (full setup elided — see existing rls/ test fixtures for the pattern)
    actor_id, target_role_id, target_user_id = await _seed_priv_escalation_case(db_session)
    await db_session.execute(
        text("SET LOCAL app.actor_id = :actor"),
        {"actor": str(actor_id)},
    )
    with pytest.raises(Exception) as exc:
        await db_session.execute(
            text(
                "INSERT INTO user_roles (auth_user_id, role_id, granted_by) "
                "VALUES (:u, :r, :g)"
            ),
            {"u": str(target_user_id), "r": str(target_role_id), "g": str(actor_id)},
        )
    assert "privilege" in str(exc.value).lower() or "escalation" in str(exc.value).lower()


async def test_priv_escalation_trigger_allows_grant_when_actor_holds_perms(
    db_session: AsyncSession,
) -> None:
    """Same setup but actor IS super_admin — INSERT succeeds."""
    ...


async def test_immutable_system_role_rejects_update(db_session: AsyncSession) -> None:
    """UPDATE on roles WHERE is_system raises."""
    with pytest.raises(Exception) as exc:
        await db_session.execute(
            text(
                "UPDATE roles SET name = 'pwned' "
                "WHERE scope = 'platform' AND key = 'super_admin' AND is_system"
            )
        )
    assert "system" in str(exc.value).lower() and "immutable" in str(exc.value).lower()


async def test_immutable_system_role_rejects_delete(db_session: AsyncSession) -> None:
    """DELETE on roles WHERE is_system raises."""
    ...


async def test_immutable_system_role_rejects_perm_change(db_session: AsyncSession) -> None:
    """INSERT/UPDATE/DELETE on role_permissions where the role is is_system raises."""
    ...


async def _seed_priv_escalation_case(
    db: AsyncSession,
) -> tuple[UUID, UUID, UUID]:
    """Returns (actor_id, target_role_id, target_user_id).

    Actor: @example.com auth user with NO user_roles grant (no perms).
    Target role: the seeded platform `admin` role.
    Target user: a different @example.com auth user.
    """
    ...  # mechanical setup — implementation in the subagent
```

(The `_seed_priv_escalation_case` body is the mechanical seeding — auth.users insert + tenants/platform_users rows as needed. The subagent fills it in by reading existing `tests/rls/` setup patterns.)

- [ ] **Step 2: Run the test, expect FAIL**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/migrations/test_0009_triggers.py -v 2>&1 | tail -25
```

Expected: tests fail because the triggers don't exist yet. If they fail for a different reason (auth.users insert path, etc.), STOP and report.

- [ ] **Step 3: Write the migration**

Create `apps/api/migrations/versions/0009_rbac_governance_triggers.py`:

```python
"""RBAC governance triggers: privilege-escalation + immutable system roles.

Spec §6.1 (privilege-escalation guard, defense in depth at the DB layer) and
§6.3 (immutable system roles).

revision: 0009
down_revision: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The actor for INSERT into user_roles is read from a session GUC the
    # backend service sets (`SET LOCAL app.actor_id = <uuid>`). If unset,
    # the trigger treats the actor as having no permissions and rejects
    # any grant of a non-empty role — failing-closed.
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_priv_escalation()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
            actor_id uuid;
            target_scope text;
            target_workspace_id uuid;
            missing_perm text;
        BEGIN
            actor_id := nullif(current_setting('app.actor_id', true), '')::uuid;
            SELECT r.scope, NEW.workspace_id
              INTO target_scope, target_workspace_id
              FROM roles r WHERE r.id = NEW.role_id;

            -- Find any permission in the target role that the actor does NOT hold.
            SELECT p.key INTO missing_perm
            FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = NEW.role_id
              AND NOT (
                CASE target_scope
                  WHEN 'platform' THEN has_platform_perm(actor_id, p.key)
                  WHEN 'workspace' THEN has_workspace_perm(actor_id, target_workspace_id, p.key)
                  ELSE false
                END
              )
            LIMIT 1;

            IF missing_perm IS NOT NULL THEN
                RAISE EXCEPTION
                  'privilege escalation denied: actor lacks permission %', missing_perm
                  USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN NEW;
        END
        $$;
    """)

    op.execute("""
        CREATE TRIGGER trg_user_roles_priv_escalation
        BEFORE INSERT ON user_roles
        FOR EACH ROW EXECUTE FUNCTION enforce_priv_escalation();
    """)

    # Immutable system roles: block UPDATE/DELETE on roles where is_system=true,
    # and block any change to role_permissions whose role is is_system.
    op.execute("""
        CREATE OR REPLACE FUNCTION reject_system_role_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (TG_OP IN ('UPDATE','DELETE')) AND (OLD.is_system) THEN
                RAISE EXCEPTION
                  'system role is immutable (role.id=%)', OLD.id
                  USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END
        $$;
    """)

    op.execute("""
        CREATE TRIGGER trg_roles_immutable_system
        BEFORE UPDATE OR DELETE ON roles
        FOR EACH ROW EXECUTE FUNCTION reject_system_role_mutation();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION reject_system_role_perm_change()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            role_is_system boolean;
            target_role_id uuid;
        BEGIN
            target_role_id := COALESCE(NEW.role_id, OLD.role_id);
            SELECT is_system INTO role_is_system FROM roles WHERE id = target_role_id;
            IF role_is_system THEN
                RAISE EXCEPTION
                  'system role permissions are immutable (role.id=%)', target_role_id
                  USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END
        $$;
    """)

    op.execute("""
        CREATE TRIGGER trg_role_perms_immutable_system
        BEFORE INSERT OR UPDATE OR DELETE ON role_permissions
        FOR EACH ROW EXECUTE FUNCTION reject_system_role_perm_change();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_user_roles_priv_escalation ON user_roles;")
    op.execute("DROP TRIGGER IF EXISTS trg_roles_immutable_system ON roles;")
    op.execute("DROP TRIGGER IF EXISTS trg_role_perms_immutable_system ON role_permissions;")
    op.execute("DROP FUNCTION IF EXISTS enforce_priv_escalation();")
    op.execute("DROP FUNCTION IF EXISTS reject_system_role_mutation();")
    op.execute("DROP FUNCTION IF EXISTS reject_system_role_perm_change();")
```

**Critical caveats the subagent must verify before writing:**

1. **Trigger SECURITY DEFINER for the priv-escalation function** so it can call `has_platform_perm`/`has_workspace_perm` cleanly — those are already SECURITY DEFINER from `0007`, so the trigger doesn't strictly need it, but mirroring the pattern is safer.
2. **`current_setting('app.actor_id', true)`** returns empty string if unset → the `nullif(...)::uuid` coerces to NULL → `has_platform_perm(NULL, ...)` returns false → trigger rejects any non-empty role grant. **This is the desired fail-closed behavior**. The backend service in Task C1 explicitly `SET LOCAL app.actor_id` per request.
3. **Reconciler at `make rbac-seed`** does `INSERT user_roles` directly when backfilling enums (P3a — `reconcile_user_roles_from_enums`). That path will now be subject to the priv-escalation trigger. **Mitigation:** the reconciler must set `app.actor_id` to the existing super_admin's id (or use a bypass GUC like `app.bypass_priv_escalation = true` that the trigger respects). Read `apps/api/src/xtrusio_api/rbac/reconcile.py:reconcile_user_roles_from_enums` BEFORE writing the trigger; if the reconciler can't easily provide an actor, add a bypass GUC and document why.

**If the bypass-GUC route is needed, add this clause at the top of `enforce_priv_escalation`:**

```sql
IF current_setting('app.bypass_priv_escalation', true) = 'on' THEN
    RETURN NEW;
END IF;
```

And document in code that ONLY the boot-time reconciler and the alembic migration code itself may set this GUC. **The bypass GUC must NEVER be set by request-scoped code.**

- [ ] **Step 4: Apply the migration**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && STARTUP_RECONCILE_TOLERANT=false uv run --directory apps/api alembic upgrade head 2>&1 | tail -10
```

Expected: `0008 -> 0009` applied.

- [ ] **Step 5: Run the migration test, expect PASS**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/migrations/test_0009_triggers.py -v 2>&1 | tail -25
```

Expected: all pass. If any fail, fix the trigger (NOT the test) until they pass.

- [ ] **Step 6: Verify downgrade is reversible**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && STARTUP_RECONCILE_TOLERANT=false uv run --directory apps/api alembic downgrade -1 2>&1 | tail -5 && STARTUP_RECONCILE_TOLERANT=false uv run --directory apps/api alembic upgrade head 2>&1 | tail -5
```

Expected: `0009 -> 0008` downgrade, then `0008 -> 0009` re-upgrade, both clean.

- [ ] **Step 7: Commit**

```bash
git add apps/api/migrations/versions/0009_rbac_governance_triggers.py apps/api/tests/migrations/test_0009_triggers.py
git commit -m "feat(rbac): 0009 — privilege-escalation + immutable-system-roles DB triggers"
```

### Task A2: Audit-write helper + ORM model

**Files:**
- Create: `apps/api/src/xtrusio_api/core/audit.py`
- Create: `apps/api/src/xtrusio_api/models/audit_log.py` (and `models/role.py` if missing)
- Create: `apps/api/tests/core/test_audit.py`
- Modify: `apps/api/tests/_cleanup.py` (add `rbac_audit_log` purge)

- [ ] **Step 1: Read existing models**

Read `apps/api/src/xtrusio_api/models/rbac.py` (the existing RBAC model file from P1). Confirm whether `Role`, `RolePermission`, `Permission`, `UserRole` models exist there. If `AuditLog` is missing, add it (next step). If `Role` is missing, add it.

- [ ] **Step 2: Write the ORM model for `rbac_audit_log`**

Append to `apps/api/src/xtrusio_api/models/rbac.py` (or create `models/audit_log.py` if the existing rbac.py is already large):

```python
class AuditLog(Base):
    __tablename__ = "rbac_audit_log"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    actor_auth_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

(Confirm against the actual `0006` migration's column types before writing — the spec's `before`/`after` are jsonb; the implementer must verify.)

- [ ] **Step 3: Write the audit-write helper**

Create `apps/api/src/xtrusio_api/core/audit.py`:

```python
"""Audit-log writer for RBAC mutations.

Every RBAC service that mutates `roles`, `role_permissions`, or `user_roles`
calls `write_audit_event(...)` within the same transaction as the mutation.
That guarantees a mutation cannot succeed without its audit row (or vice versa)
— if the audit insert fails, the caller's commit rolls back.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def write_audit_event(
    db: AsyncSession,
    *,
    actor_id: UUID,
    action: str,
    target_type: str,
    target_id: UUID,
    scope: str,
    workspace_id: UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Insert one row into rbac_audit_log. Caller owns the surrounding tx."""
    await db.execute(
        text(
            "INSERT INTO rbac_audit_log "
            "(actor_auth_user_id, action, target_type, target_id, scope, "
            " workspace_id, before, after) "
            "VALUES (:a, :act, :tt, :tid, :s, :w, "
            "        CAST(:b AS jsonb), CAST(:af AS jsonb))"
        ),
        {
            "a": str(actor_id),
            "act": action,
            "tt": target_type,
            "tid": str(target_id),
            "s": scope,
            "w": str(workspace_id) if workspace_id else None,
            "b": _json_or_null(before),
            "af": _json_or_null(after),
        },
    )


def _json_or_null(payload: dict[str, Any] | None) -> str | None:
    import json
    return None if payload is None else json.dumps(payload, default=str)
```

- [ ] **Step 4: Write unit tests for the writer**

Create `apps/api/tests/core/test_audit.py`:

```python
"""write_audit_event correctness."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.audit import write_audit_event

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_writes_one_row_with_all_fields(db_session: AsyncSession) -> None:
    actor = uuid4()
    target = uuid4()
    await write_audit_event(
        db_session,
        actor_id=actor,
        action="test_action",
        target_type="role",
        target_id=target,
        scope="platform",
        before={"name": "old"},
        after={"name": "new"},
    )
    row = (
        await db_session.execute(
            text(
                "SELECT actor_auth_user_id, action, target_type, target_id, scope, "
                "workspace_id, before, after FROM rbac_audit_log "
                "WHERE actor_auth_user_id = :a AND target_id = :t"
            ),
            {"a": str(actor), "t": str(target)},
        )
    ).one()
    assert row.action == "test_action"
    assert row.before == {"name": "old"}
    assert row.after == {"name": "new"}
    assert row.scope == "platform"
    assert row.workspace_id is None

    # Cleanup so the row doesn't leak — actor is uuid4(), not @example.com,
    # so _cleanup.py won't catch it.
    await db_session.execute(
        text("DELETE FROM rbac_audit_log WHERE actor_auth_user_id = :a"),
        {"a": str(actor)},
    )
    await db_session.commit()


async def test_rolls_back_if_caller_does_not_commit(db_session: AsyncSession) -> None:
    """If the caller's session never commits, the audit row never lands either."""
    actor = uuid4()
    target = uuid4()
    await write_audit_event(
        db_session, actor_id=actor, action="x", target_type="role",
        target_id=target, scope="platform",
    )
    # Don't commit; open a new session and assert no row visible.
    async with db_session.bind.connect() as conn:  # type: ignore[union-attr]
        result = await conn.execute(
            text(
                "SELECT count(*) FROM rbac_audit_log WHERE actor_auth_user_id = :a"
            ),
            {"a": str(actor)},
        )
        assert result.scalar_one() == 0
```

- [ ] **Step 5: Extend `_cleanup.py`**

Add to `apps/api/tests/_cleanup.py` in the FK-safe delete order, BEFORE `platform_users`/`auth_users` deletes:

```python
# Add to id_stmts list (inside the `if test_ids:` branch):
("rbac_audit_log", "DELETE FROM rbac_audit_log WHERE actor_auth_user_id = ANY(:ids)"),
("user_roles_test", "DELETE FROM user_roles WHERE auth_user_id = ANY(:ids)"),
("roles_custom_test", (
    "DELETE FROM roles WHERE created_by = ANY(:ids) AND NOT is_system"
)),
```

(Order matters: `user_roles` before `roles` before `platform_users`/`auth_users`.)

- [ ] **Step 6: Run audit + cleanup tests**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && STARTUP_RECONCILE_TOLERANT=false uv run --directory apps/api python -m tests._cleanup && STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/core/test_audit.py -v 2>&1 | tail -20
```

Expected: pass.

- [ ] **Step 7: Lint + commit**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && uv run ruff check apps/api/src/xtrusio_api/core/audit.py apps/api/src/xtrusio_api/models/rbac.py apps/api/tests/core/test_audit.py apps/api/tests/_cleanup.py && uv run ruff format --check apps/api/src/xtrusio_api/core/audit.py apps/api/src/xtrusio_api/models/rbac.py apps/api/tests/core/test_audit.py apps/api/tests/_cleanup.py && uv run mypy apps/api/src/xtrusio_api/core/audit.py apps/api/src/xtrusio_api/models/rbac.py
```

Then:

```bash
git add apps/api/src/xtrusio_api/core/audit.py apps/api/src/xtrusio_api/models/rbac.py apps/api/tests/core/test_audit.py apps/api/tests/_cleanup.py
git commit -m "feat(rbac): audit-write helper + AuditLog ORM model + cleanup coverage"
```

### Slice A end-of-slice gate (controller-run)

- [ ] `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check` — expect green (assuming type-the-tests merged first).

---

## Slice B — Platform-role CRUD

Goal: super_admin can create, list, get, update, and delete CUSTOM platform roles. System roles remain immutable (enforced by the DB trigger from A1 + a service-layer pre-check for friendlier 403/422 errors).

### Task B1: Schemas

**Files:**
- Create: `apps/api/src/xtrusio_api/schemas/platform_role.py`

- [ ] **Step 1: Write the file**

```python
"""Pydantic schemas for platform-role endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlatformRoleIn(BaseModel):
    """Create-payload for a custom platform role."""
    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permission_keys: list[str] = Field(default_factory=list)


class PlatformRolePatch(BaseModel):
    """Partial-update payload. None means "leave unchanged"."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    permission_keys: list[str] | None = None


class PlatformRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    key: str
    name: str
    description: str | None
    is_system: bool
    permission_keys: list[str]
    created_at: datetime
    updated_at: datetime


class PlatformRolesPage(BaseModel):
    items: list[PlatformRoleOut]
    next_cursor: str | None = None


class PlatformRoleGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    auth_user_id: UUID
    role_id: UUID
    role_key: str
    granted_at: datetime
    granted_by: UUID | None


class PlatformRoleGrantsPage(BaseModel):
    items: list[PlatformRoleGrantOut]
    next_cursor: str | None = None
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/xtrusio_api/schemas/platform_role.py
git commit -m "feat(rbac): platform-role pydantic schemas"
```

### Task B2: Service — CRUD operations

**Files:**
- Create: `apps/api/src/xtrusio_api/services/platform_roles.py`
- Test: `apps/api/tests/services/test_platform_roles.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/services/test_platform_roles.py` with tests for:
- `create_platform_role` happy path: returns row with `is_system=False`, attaches the requested permissions
- `create_platform_role` raises on duplicate key (use a freshly seeded key per test to avoid collisions across runs; `@example.com`-related cleanup handles)
- `create_platform_role` raises if `permission_keys` contains an unknown key
- `create_platform_role` raises if any `permission_keys` is workspace-scope (scope mismatch)
- `list_platform_roles` returns both system + custom, paginated, newest first
- `get_platform_role` returns one or raises `LookupError`
- `update_platform_role` happy path: changes name/description/permission set; emits audit event; rejects mutation when target is is_system (raises `SystemRoleImmutableError`)
- `delete_platform_role` happy path on custom role; rejects on system role; cascades user_roles deletes via DB FK or explicit clean (verify migration `0006`'s FK behaviour first)

The test bodies use `existing_super_admin` as the actor; they use direct DB inserts to seed an actor with the right perms; they call the service with `actor_id=existing_super_admin.id`.

Each test that produces audit rows should verify one row was inserted into `rbac_audit_log` with the expected `action` value.

(Implementer fills in test bodies — the structure is mechanical, mirroring existing service-level tests.)

- [ ] **Step 2: Implement the service**

Create `apps/api/src/xtrusio_api/services/platform_roles.py`:

```python
"""Platform-role CRUD service.

Every mutation:
1. SETs `app.actor_id` in the surrounding tx so the priv-escalation trigger
   sees the actor (only matters for grant/revoke, but we set it uniformly so
   the service layer is consistent).
2. Writes an audit event via core.audit.write_audit_event.

Authorization gate (`platform.roles.manage`) is the caller's responsibility
(applied at the route layer via require_permission). The service does NOT
re-check the gate — but it DOES enforce immutable-system-roles at the service
layer as a friendlier 422/403 path before the DB trigger fires.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import write_audit_event
from ..core.pagination import encode_cursor


class RoleNotFoundError(LookupError):
    pass


class RoleKeyTakenError(Exception):
    pass


class SystemRoleImmutableError(Exception):
    pass


class UnknownPermissionError(Exception):
    pass


class ScopeMismatchError(Exception):
    pass


async def create_platform_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    key: str,
    name: str,
    description: str | None,
    permission_keys: list[str],
) -> dict[str, Any]:
    """Create a custom platform role with permissions. Returns the full row dict
    including `permission_keys` for serialization. Caller owns the tx."""
    await _set_actor(db, actor_id)
    # Validate permission keys: all must exist and be platform-scope.
    await _validate_perm_keys(db, scope="platform", keys=permission_keys)
    # Insert role.
    row = (
        await db.execute(
            text(
                "INSERT INTO roles (scope, key, name, description, is_system, created_by) "
                "VALUES ('platform', :key, :name, :desc, false, :actor) "
                "RETURNING id, key, name, description, is_system, created_at, updated_at"
            ),
            {"key": key, "name": name, "desc": description, "actor": str(actor_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise RuntimeError("INSERT roles RETURNING produced no row")
    role_id = row["id"]
    # Attach permissions.
    if permission_keys:
        await db.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT :rid, p.id FROM permissions p "
                "WHERE p.key = ANY(:keys)"
            ),
            {"rid": str(role_id), "keys": permission_keys},
        )
    # Audit.
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_role.create",
        target_type="role",
        target_id=role_id,
        scope="platform",
        after={"key": key, "name": name, "permission_keys": permission_keys},
    )
    return {**dict(row), "permission_keys": permission_keys}


async def list_platform_roles(
    db: AsyncSession,
    *,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    # ... (cursor-paginated select on roles WHERE scope='platform'
    #      ORDER BY created_at DESC, id DESC, with permission_keys aggregated
    #      via a subquery on role_permissions JOIN permissions)
    ...


async def get_platform_role(
    db: AsyncSession, *, role_id: UUID
) -> dict[str, Any]:
    # ... raises RoleNotFoundError
    ...


async def update_platform_role(
    db: AsyncSession,
    *,
    actor_id: UUID,
    role_id: UUID,
    name: str | None,
    description: str | None,
    permission_keys: list[str] | None,
) -> dict[str, Any]:
    await _set_actor(db, actor_id)
    # Load existing row.
    existing = await _load_role(db, role_id)
    if existing is None:
        raise RoleNotFoundError(str(role_id))
    if existing["is_system"]:
        raise SystemRoleImmutableError(str(role_id))
    # Apply changes selectively.
    before = {**existing}
    # ... UPDATE roles SET name=..., description=..., updated_at=now()
    # ... if permission_keys is not None: validate scope, then DELETE+INSERT
    #     role_permissions for this role inside a single tx
    after = await _load_role(db, role_id)
    await write_audit_event(
        db, actor_id=actor_id, action="platform_role.update",
        target_type="role", target_id=role_id, scope="platform",
        before=before, after=after,
    )
    return after  # type: ignore[return-value]


async def delete_platform_role(
    db: AsyncSession, *, actor_id: UUID, role_id: UUID
) -> None:
    await _set_actor(db, actor_id)
    existing = await _load_role(db, role_id)
    if existing is None:
        raise RoleNotFoundError(str(role_id))
    if existing["is_system"]:
        raise SystemRoleImmutableError(str(role_id))
    # DELETE the role. user_roles rows referencing it cascade (verify FK in 0006).
    await db.execute(text("DELETE FROM roles WHERE id = :id"), {"id": str(role_id)})
    await write_audit_event(
        db, actor_id=actor_id, action="platform_role.delete",
        target_type="role", target_id=role_id, scope="platform",
        before=existing,
    )


# --- helpers ---


async def _set_actor(db: AsyncSession, actor_id: UUID) -> None:
    """Tag the tx with the actor so the priv-escalation trigger sees it."""
    await db.execute(
        text("SELECT set_config('app.actor_id', :a, true)"),
        {"a": str(actor_id)},
    )


async def _validate_perm_keys(
    db: AsyncSession, *, scope: str, keys: list[str]
) -> None:
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
        raise ScopeMismatchError(
            f"keys not in scope={scope!r}: {sorted(wrong_scope)}"
        )


async def _load_role(db: AsyncSession, role_id: UUID) -> dict[str, Any] | None:
    # ... (load roles row + aggregated permission_keys via subquery)
    ...
```

(The implementer fills in the elided helpers and the list/get bodies — they're mechanical with the established cursor-pagination pattern from P3.5.)

**Important:** `delete_platform_role` relies on FK behaviour of `user_roles.role_id`. The implementer MUST check migration `0006`: if FK is `ON DELETE CASCADE`, the cascade is automatic; if `ON DELETE RESTRICT`, the service must DELETE `user_roles WHERE role_id = :id` first. Pick the policy that matches `0006`; if `0006` is RESTRICT, the service does the explicit cleanup AND records per-grant audit events. If RESTRICT but no per-grant audits needed (mass delete is one logical action), a single role-delete audit row with `before = {grants: [...]}` captures it.

- [ ] **Step 3: Run tests, iterate until pass**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && STARTUP_RECONCILE_TOLERANT=false uv run --directory apps/api python -m tests._cleanup && STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_platform_roles.py -v 2>&1 | tail -30
```

- [ ] **Step 4: Lint + commit**

```bash
git add apps/api/src/xtrusio_api/services/platform_roles.py apps/api/tests/services/test_platform_roles.py
git commit -m "feat(rbac): platform-role CRUD service + audit + immutable-system guard"
```

### Task B3: Route layer

**Files:**
- Create: `apps/api/src/xtrusio_api/routes/platform_roles.py`
- Test: `apps/api/tests/routes/test_platform_roles.py`
- Modify: `apps/api/src/xtrusio_api/main.py` (wire router)

- [ ] **Step 1: Write the routes**

Endpoints (all gated by `require_permission(db, user.user_id, "platform.roles.manage")`):
- `GET /api/platform/roles?cursor=&limit=`
- `POST /api/platform/roles` → 201 + body
- `GET /api/platform/roles/{role_id}` → 200 / 404
- `PATCH /api/platform/roles/{role_id}` → 200 / 404 / 422 (system role)
- `DELETE /api/platform/roles/{role_id}` → 204 / 404 / 422 (system role)

Standard FastAPI patterns mirroring `routes/tenants.py`. Validation 400s come from Pydantic; service exceptions map to HTTP codes:

| Exception | HTTP |
|---|---|
| `RoleNotFoundError` | 404 |
| `RoleKeyTakenError` | 409 |
| `SystemRoleImmutableError` | 422 (with `detail: "system_role_immutable"`) |
| `UnknownPermissionError` | 422 (with `detail` listing keys) |
| `ScopeMismatchError` | 422 |

- [ ] **Step 2: Wire into `main.py`**

Add `from .routes import platform_roles as platform_roles_routes` and `app.include_router(platform_roles_routes.router)`.

- [ ] **Step 3: Tests**

Route-level: auth (401 no token, 403 with token lacking `platform.roles.manage`, 200 with super_admin), validation errors, pagination round-trip, system-role mutation rejection.

- [ ] **Step 4: Lint + commit**

```bash
git add apps/api/src/xtrusio_api/routes/platform_roles.py apps/api/src/xtrusio_api/main.py apps/api/tests/routes/test_platform_roles.py
git commit -m "feat(rbac): GET/POST/PATCH/DELETE /api/platform/roles endpoints"
```

### Slice B end-of-slice gate

- [ ] `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check`

---

## Slice C — Role-grants + governance enforcement

### Task C1: Grant/revoke service

**Files:**
- Create: `apps/api/src/xtrusio_api/services/platform_role_grants.py`
- Test: `apps/api/tests/services/test_platform_role_grants.py`

Service surface:
- `grant_platform_role(db, *, actor_id, target_user_id, role_id)` — insert `user_roles`; the DB trigger from A1 enforces priv-escalation; service-layer pre-checks for friendlier errors:
  - Target user must exist in `platform_users`
  - Target role must exist and be platform-scope
  - Service-layer priv-escalation check mirrors the trigger (returns `PrivilegeEscalationError` BEFORE the DB raises, for cleaner 403)
  - Single-super_admin: if `role.key == 'super_admin'`, check `SELECT count(*) FROM user_roles ur JOIN roles r ON ... WHERE r.key='super_admin'` and raise `SingleSuperAdminError` if there's already one
  - Audit event `platform_role.grant`
- `revoke_platform_role_grant(db, *, actor_id, grant_id)` — delete `user_roles` row; audit event `platform_role.revoke`; same priv-escalation guard for the role-being-revoked
- `list_platform_role_grants(db, *, user_id, cursor, limit) -> (rows, next_cursor)` — list a single platform user's grants, paginated

Errors:
- `PlatformUserNotFoundError` → 404
- `RoleNotFoundError` → 404
- `RoleScopeMismatchError` → 422 (workspace role on platform user)
- `PrivilegeEscalationError` → 403
- `SingleSuperAdminError` → 409 (with `detail: "single_super_admin_invariant"`)
- `GrantNotFoundError` → 404

- [ ] **Step 1: Tests first**
- [ ] **Step 2: Implement**
- [ ] **Step 3: Run + lint + commit**

```bash
git add apps/api/src/xtrusio_api/services/platform_role_grants.py apps/api/tests/services/test_platform_role_grants.py
git commit -m "feat(rbac): platform-role grant/revoke + priv-escalation + single-super_admin guards"
```

### Task C2: Route layer for grants

**Files:**
- Modify: `apps/api/src/xtrusio_api/routes/platform_roles.py` (extend with grant/revoke routes — OR split into a new `routes/platform_role_grants.py` if the file approaches 200 LoC; honor §1 file-size rules)
- Test: extend `apps/api/tests/routes/test_platform_roles.py` (or new file matching the split)

Endpoints:
- `GET /api/platform/users/{user_id}/roles?cursor=&limit=` — list grants for a platform user (gate: `platform.users.read` OR `platform.users.manage`)
- `POST /api/platform/users/{user_id}/roles` body `{"role_id": "..."}` → 201 (gate: `platform.users.manage`)
- `DELETE /api/platform/users/{user_id}/roles/{grant_id}` → 204 (gate: `platform.users.manage`)

- [ ] **Step 1: Tests**
- [ ] **Step 2: Routes + main.py wire-up**
- [ ] **Step 3: Lint + commit**

```bash
git add apps/api/src/xtrusio_api/routes/platform_roles.py apps/api/tests/routes/test_platform_roles.py apps/api/src/xtrusio_api/main.py
git commit -m "feat(rbac): platform user role-grant REST endpoints"
```

### Slice C end-of-slice gate

- [ ] `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check`

---

## Slice D — Audit-log viewer

### Task D1: Service + route

**Files:**
- Create: `apps/api/src/xtrusio_api/services/platform_audit_log.py`
- Create: `apps/api/src/xtrusio_api/schemas/audit_log.py`
- Create: `apps/api/src/xtrusio_api/routes/platform_audit_log.py`
- Test: `apps/api/tests/services/test_platform_audit_log.py`
- Test: `apps/api/tests/routes/test_platform_audit_log.py`
- Modify: `apps/api/src/xtrusio_api/main.py`

Schema `AuditEventOut`:
- `id: UUID`
- `actor_auth_user_id: UUID`
- `action: str`
- `target_type: str`
- `target_id: UUID`
- `scope: str`
- `workspace_id: UUID | None`
- `before: dict | None`
- `after: dict | None`
- `created_at: datetime`

Service:
- `list_platform_audit_events(db, *, cursor, limit) -> (rows, next_cursor)` — `SELECT ... WHERE scope = 'platform' ORDER BY created_at DESC, id DESC` (cursor + limit per the established pattern)

Route:
- `GET /api/platform/audit-log?cursor=&limit=` — gate: `platform.audit.read`

Tests:
- Service: seeds 3 audit events via `write_audit_event`, pagination round-trip, scope filter (a workspace-scope event does NOT appear)
- Route: 401 no token, 403 with token lacking `platform.audit.read`, 200 with the right grant, cursor 400, pagination round-trip

- [ ] **Step 1: Tests, schema, service, route in order**
- [ ] **Step 2: Wire main.py**
- [ ] **Step 3: Lint + commit**

```bash
git add apps/api/src/xtrusio_api/services/platform_audit_log.py apps/api/src/xtrusio_api/schemas/audit_log.py apps/api/src/xtrusio_api/routes/platform_audit_log.py apps/api/src/xtrusio_api/main.py apps/api/tests/services/test_platform_audit_log.py apps/api/tests/routes/test_platform_audit_log.py
git commit -m "feat(rbac): GET /api/platform/audit-log (cursor-paginated, platform.audit.read gated)"
```

### Slice D end-of-slice gate

- [ ] `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check`

---

## Wrap

### Task W1: Final Opus code-quality review

Dispatch one Opus agent against the full branch diff. Focus areas:
- Migration 0009 reversibility (downgrade exercised in A1 step 6 — confirm)
- Trigger behaviour under the reconciler boot path (does `app.bypass_priv_escalation` get set if needed? Or does the reconciler set `app.actor_id` to the super_admin?)
- Audit-log writes are inside the same tx as the mutation (no partial state)
- Privilege-escalation guard implemented at BOTH service layer AND DB trigger (defense in depth)
- Single-super_admin: DB partial unique index + friendly service-layer check (no race between the two)
- Every new endpoint paginates (the B5 invariant test from P3.5 should pick up the new endpoints automatically — verify)
- No new mypy errors on strict; no broad `except Exception` introduced
- No new permission keys added (catalog should be untouched)

Resolve any blocking findings.

### Task W2: PR body + push + open + merge

- [ ] Write `docs/superpowers/PR-rbac-p4-body.md` summarizing the 4 slices, governance enforced both at service and DB layers, no UI changes.

- [ ] `git push -u origin rbac-p4-platform-admin`

- [ ] `gh pr create --base main --head rbac-p4-platform-admin --title "P4 — Platform RBAC admin (API + governance)" --body-file docs/superpowers/PR-rbac-p4-body.md`

- [ ] Watch CI (will be UNSTABLE/red until `xtrusio-ci` secrets are configured — expected; advisory). Local `make check` is the contract.

- [ ] On user's go-ahead: `gh pr merge <n> --merge`. Verify `gh pr view <n> --json state` = MERGED.

- [ ] Update HANDOFF.md: add P4 to the Done table; mark "P4 next" item as done; move next pointer to P5. Open a small docs PR for the HANDOFF update and merge it.

- [ ] Cleanup: `git checkout main && git pull && git push origin --delete rbac-p4-platform-admin && git branch -D rbac-p4-platform-admin`.

---

## Self-review checklist

1. **Spec coverage:** §4 catalog (unchanged), §6.1 priv-escalation (service + trigger), §6.2 single super_admin (DB index from P1 + service check), §6.3 immutable system roles (trigger + service), §6.5 audit log (writer + viewer). ✅
2. **Placeholder scan:** every step has concrete code or a documented `...` for mechanical bodies that mirror an existing pattern. The `...` placeholders are limited to: helper bodies mirroring P3.5 cursor pagination, test bodies mirroring existing service tests, role-deletion-with-FK behaviour (resolved at implementation time after reading `0006`). All are flagged for the implementer to expand. ✅
3. **Type consistency:** `actor_id` everywhere (not `user_id` or `granted_by`); `permission_keys: list[str]` everywhere; `cursor: tuple[datetime, UUID] | None` matches the P3.5 service signatures. ✅
4. **Out-of-scope discipline:** no frontend, no workspace RBAC, no catalog edits, no enum-column drop. ✅
5. **User memory respect:** lean review workflow, Opus subagents, no Co-Authored-By, no hardcoded config, test data hygiene, `STARTUP_RECONCILE_TOLERANT=false` prefix on every test run. ✅

---

## Execution choice

Once the [type-the-tests plan](./2026-05-20-type-the-tests.md) lands first, execute P4 via `superpowers:subagent-driven-development` — one Opus implementer per task, controller-run end-of-slice gates and final code-quality review, one PR, one merge.
