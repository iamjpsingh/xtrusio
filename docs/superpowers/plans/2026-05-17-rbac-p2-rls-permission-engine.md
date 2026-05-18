# RBAC P2 — RLS Permission Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the DB-enforced permission resolvers `has_platform_perm` / `has_workspace_perm` (read user→user_roles→role_permissions→permissions), supersede the migration-`0003` enum helpers by rewriting their bodies to delegate to the resolvers (every existing `0003`/`0004` policy keeps working, now sourced from the new tables → instant revocation), and replace `0006`'s permissive interim RBAC-table RLS policies with perm-aware ones — all reversible, with a full RLS test matrix.

**Architecture:** One pure-raw-SQL Alembic migration `0007_rls_permission_engine` (`down_revision="0006"`). Two `SECURITY DEFINER STABLE` resolver functions bypass RLS internally (no recursion — the proven `0003` technique) and are the single source of truth that **both RLS policies and (in P3) the backend** will call. The three `0003` helpers (`is_super_admin`, `is_tenant_owner_or_admin`, `is_tenant_member`) are `CREATE OR REPLACE`d to delegate — signatures unchanged, so the ~13 existing policies in `0003`/`0004` that call them need zero edits. The `0006` interim `*_authenticated_read USING(true)` / `rbac_audit_log_no_read` policies are dropped and replaced with resolver-gated SELECT policies (removing the cross-tenant `user_roles` over-read the P1 review flagged). RLS tests follow the established `tests/rls/` hygiene pattern.

**Tech Stack:** Postgres (Supabase managed), Alembic raw `op.execute`, asyncpg, pytest + pytest-asyncio, `uv`, `make`.

**Spec:** `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` §5 (single source of truth), §6 (governance), §10 row P2, §11. **Builds on merged P1** (`main` @ `6be1e2f`: migration `0006`, `rbac/catalog.py`, system-role seeds).

---

## Conventions that apply to EVERY task (read once)

- Branch: `rbac-p2-rls-engine` (already cut from merged `main`). Do NOT switch branches.
- Migrations are pure raw SQL via `op.execute`, ONE statement per call (asyncpg rejects multi-statement `text()`), no app imports, header/typing exactly like `0006`.
- Apply/revert: `make migrate` / `make migrate-down` against the managed Supabase DB (holds the one real super_admin `admin@xtrusio.com`; after P1 it has the seeded system roles + that super_admin backfilled to a `user_roles` grant to role id `00000000-0000-0000-0000-0000000000a1`). `make migrate-down` must restore the exact `0006` end-state.
- Backend tests: `uv run --directory apps/api pytest <path> -v`. RLS test modules: `pytestmark = pytest.mark.asyncio(loop_scope="session")`; use the `rls_as` fixture + `existing_super_admin` fixture from `tests/rls/conftest.py` / `tests/conftest.py`.
- **Test-data hygiene (mandatory):** never create a `super_admin`; positive super_admin cases use the read-only `existing_super_admin` fixture. Other users are ephemeral `auth.users` rows with `@example.com` emails created in a privileged `SessionLocal()` and deleted in a `finally:` (mirror `tests/rls/test_platform_settings_rls.py` exactly). Any ephemeral `user_roles`/`roles`/`tenants` rows created for a test are torn down in the same `finally:`. No `@example.com` row may survive a test.
- Lint/type before commit: `uv run ruff check apps/api` + `uv run mypy --strict apps/api/src` — zero NEW errors (accepted pre-existing baseline: 4 ruff `I001` in `scripts/bootstrap.py`+`services/{signup,platform_invites,tenant_invites}.py`; 1 `jose` mypy in `core/auth.py`).
- Pre-existing accepted env-failures (do NOT "fix"): `tests/routes/test_signup.py::test_signup_status_default_false` + `::test_signup_disabled_returns_403` (managed DB `signups_enabled=true`).
- Commit with repo git identity. **NO `Co-Authored-By` trailer.** TDD order. Single Alembic head after this plan: `0007`.

---

## Permission-key mapping (the semantic contract — verified behaviour-preserving)

The catalog (`apps/api/src/xtrusio_api/rbac/catalog.py`, merged) + the `0006` system-role seeds + the reconciler give these system-role permission sets:

- platform `super_admin` = ALL 9 `platform.*` keys (incl. `platform.roles.manage`).
- platform `admin` = the 8 `platform.*` keys EXCEPT `platform.roles.manage`.
- workspace `owner` = ALL 7 `workspace.*` keys (incl. `workspace.roles.manage`, `workspace.members.manage`).
- workspace `admin` = the 6 `workspace.*` keys EXCEPT `workspace.roles.manage` (so it HAS `workspace.members.manage`).
- workspace `editor` / `read_only` = exactly `workspace.members.read` + `workspace.settings.read`.

Each `0003` helper becomes **`new_resolver OR original_0003_enum_check`** — a true superset
(spec §5, corrected). Pure delegation (resolver only) is NOT behaviour-preserving in the P2→P3
window and was proven to break the pre-RBAC `tests/rls/` suite (passes at `0006`, fails under
pure `0007`) because P1's backfill is a one-time snapshot and enum-era onboarding/invites keep
creating `tenant_memberships`/`platform_users` rows with no `user_roles` grant until P3:

| `0003` helper | Old (`0003`) truth set | Transition-safe body (P2) | Result |
|---|---|---|---|
| `is_super_admin(uid)` | `platform_users.role='super_admin' AND is_active` | `has_platform_perm(uid,'platform.roles.manage')` **OR** that exact enum check | ⊒ old; equal where only enum data; + engine path (instant revoke) |
| `is_tenant_owner_or_admin(uid,tid)` | `tenant_memberships.role IN ('owner','admin')` | `has_workspace_perm(uid,tid,'workspace.members.manage')` **OR** that exact enum check | ⊒ old (owner+admin still pass via enum) |
| `is_tenant_member(uid,tid)` | any `tenant_memberships` row for (uid,tid) | `EXISTS user_roles(uid,workspace_id=tid)` **OR** any `tenant_memberships` row | ⊒ old (any member still passes via enum) |

Because each body is a superset that equals the `0003` truth set wherever only enum data exists,
**every pre-existing `tests/rls/` test passes unchanged** (they grant via fresh `tenant_memberships`
rows → the enum disjunct keeps them visible) — that suite is the regression guard. RBAC-granted
principals additionally resolve via the engine (instant revocation). All bodies stay
`SECURITY DEFINER` so the legacy `EXISTS` subqueries don't recurse (the `0003` technique). **P3
retires the legacy disjunct** once `user_roles` is authoritative.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/migrations/versions/0007_rls_permission_engine.py` | NEW. `has_platform_perm`/`has_workspace_perm`/`can_manage_role` resolvers; `CREATE OR REPLACE` the 3 `0003` helpers to delegate; drop `0006` interim RBAC-table policies, add perm-aware SELECT policies; reversible `downgrade()` restoring `0006`+`0003` verbatim. |
| `apps/api/tests/rls/test_permission_engine_rls.py` | NEW. Resolver correctness + helper-delegation behaviour-preservation + RBAC-table perm-aware-policy matrix, using the `tests/rls` hygiene pattern. |

No app/model/Python source changes in P2 (the backend still uses enum reads until P3; P2 only changes the DB layer + adds tests).

---

### Task 1: Migration `0007` — resolver functions

**Files:**
- Create: `apps/api/migrations/versions/0007_rls_permission_engine.py`
- Test: `apps/api/tests/rls/test_permission_engine_rls.py` (resolver section)

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/rls/test_permission_engine_rls.py`:

```python
"""P2 RLS permission engine — resolver correctness, helper delegation,
RBAC-table perm-aware policies. Run `make migrate` first.

Hygiene: positive super_admin cases use the read-only `existing_super_admin`
fixture; every other principal is an ephemeral @example.com auth.users row
(+ ephemeral user_roles/roles/tenants) torn down in `finally`. No @example.com
row survives a test (mirrors tests/rls/test_platform_settings_rls.py)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

from tests.rls.conftest import RlsAs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _scalar(sql: str, **params: object) -> object:
    async with SessionLocal() as s:
        return (await s.execute(text(sql), params)).scalar_one()


async def test_resolver_functions_exist_and_are_security_definer() -> None:
    rows = (
        await _scalar_all(
            "SELECT proname FROM pg_proc WHERE proname = ANY(:n) AND prosecdef",
            n=["has_platform_perm", "has_workspace_perm", "can_manage_role"],
        )
    )
    assert set(rows) == {"has_platform_perm", "has_workspace_perm", "can_manage_role"}


async def test_existing_super_admin_has_platform_roles_manage(
    existing_super_admin: PlatformUser,
) -> None:
    got = await _scalar(
        "SELECT has_platform_perm(:u, 'platform.roles.manage')",
        u=str(existing_super_admin.id),
    )
    assert got is True


async def test_unknown_user_has_no_platform_perm() -> None:
    got = await _scalar(
        "SELECT has_platform_perm(:u, 'platform.roles.manage')", u=str(uuid4())
    )
    assert got is False


async def test_deprecated_permission_does_not_grant(
    existing_super_admin: PlatformUser,
) -> None:
    # A perm key not in the catalog can never resolve true (no permissions row,
    # or a soft-deprecated one is excluded by the resolver).
    got = await _scalar(
        "SELECT has_platform_perm(:u, 'platform.does.not.exist')",
        u=str(existing_super_admin.id),
    )
    assert got is False
```

Add this helper near the top (after the imports), used by `test_resolver_functions_exist...`:

```python
async def _scalar_all(sql: str, **params: object) -> list[object]:
    async with SessionLocal() as s:
        return list((await s.execute(text(sql), params)).scalars().all())
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run --directory apps/api pytest tests/rls/test_permission_engine_rls.py -v`
Expected: FAIL — functions don't exist yet (and the migration file is absent).

- [ ] **Step 3: Create the migration with the resolvers**

Create `apps/api/migrations/versions/0007_rls_permission_engine.py` with the header + `upgrade()` containing ONLY the resolver section below (helpers/policies are Tasks 2–3), and a `downgrade()` that drops exactly what this task adds:

```python
"""RLS permission engine: has_platform_perm/has_workspace_perm resolvers,
delegate the 0003 enum helpers, perm-aware RBAC-table policies.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-17

Spec: docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md §5/§6.
Pure raw SQL. Resolvers are SECURITY DEFINER (bypass RLS internally — no
recursion, the 0003 technique) and are the single source of truth both RLS
and the P3 backend call.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # has_platform_perm(uid, perm_key): true iff uid holds a platform-scope
    # role (user_roles.workspace_id IS NULL) whose role_permissions include a
    # NON-deprecated platform permission with that key.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION has_platform_perm(uid uuid, perm_key text)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                            AND r.scope = 'platform'
                            AND r.workspace_id IS NULL
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.auth_user_id = uid
                  AND ur.workspace_id IS NULL
                  AND p.scope = 'platform'
                  AND p.key = perm_key
                  AND NOT p.is_deprecated
            )
        $$
        """
    )
    op.execute("REVOKE EXECUTE ON FUNCTION has_platform_perm(uuid, text) FROM public")
    op.execute("GRANT EXECUTE ON FUNCTION has_platform_perm(uuid, text) TO authenticated")

    # has_workspace_perm(uid, tid, perm_key): true iff uid holds a
    # workspace-scope role for THAT workspace whose role_permissions include a
    # NON-deprecated workspace permission with that key.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION has_workspace_perm(uid uuid, tid uuid, perm_key text)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                            AND r.scope = 'workspace'
                            AND r.workspace_id = tid
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.auth_user_id = uid
                  AND ur.workspace_id = tid
                  AND p.scope = 'workspace'
                  AND p.key = perm_key
                  AND NOT p.is_deprecated
            )
        $$
        """
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION has_workspace_perm(uuid, uuid, text) FROM public"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION has_workspace_perm(uuid, uuid, text) TO authenticated"
    )

    # can_manage_role(uid, role_id): SECURITY DEFINER so the role_permissions
    # SELECT policy can resolve a role's scope/workspace WITHOUT triggering
    # roles-table RLS recursion. True iff uid may manage that role.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION can_manage_role(uid uuid, rid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM roles r
                WHERE r.id = rid
                  AND (
                    (r.scope = 'platform'
                       AND has_platform_perm(uid, 'platform.roles.manage'))
                 OR (r.scope = 'workspace'
                       AND has_workspace_perm(uid, r.workspace_id, 'workspace.roles.manage'))
                  )
            )
        $$
        """
    )
    op.execute("REVOKE EXECUTE ON FUNCTION can_manage_role(uuid, uuid) FROM public")
    op.execute("GRANT EXECUTE ON FUNCTION can_manage_role(uuid, uuid) TO authenticated")

    # Helpers + policies: Tasks 2 & 3 add BELOW THIS LINE (same upgrade()).


def downgrade() -> None:
    # Policy/helper restoration: Tasks 2 & 3 add ABOVE the function drops.
    op.execute("DROP FUNCTION IF EXISTS can_manage_role(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS has_workspace_perm(uuid, uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS has_platform_perm(uuid, text)")
```

- [ ] **Step 4: Apply + test**

```bash
make migrate
uv run --directory apps/api pytest tests/rls/test_permission_engine_rls.py -v
```
Expected: the 4 resolver tests PASS (`existing_super_admin` resolves `platform.roles.manage` true via the P1 backfill grant; unknown user / unknown key false).

- [ ] **Step 5: Reversibility + commit**

```bash
make migrate-down && uv run --directory apps/api alembic current   # must show 0006
make migrate                                                       # re-apply
uv run --directory apps/api pytest tests/rls/test_permission_engine_rls.py -v
uv run ruff check apps/api && uv run mypy --strict apps/api/src
git add apps/api/migrations/versions/0007_rls_permission_engine.py apps/api/tests/rls/test_permission_engine_rls.py
git commit -m "feat(db): 0007 has_platform_perm/has_workspace_perm/can_manage_role resolvers"
```

---

### Task 2: Delegate the `0003` enum helpers to the resolvers

**Files:**
- Modify: `apps/api/migrations/versions/0007_rls_permission_engine.py` (extend `upgrade()` + `downgrade()`)
- Modify: `apps/api/tests/rls/test_permission_engine_rls.py` (append delegation tests)

- [ ] **Step 1: Append the failing tests**

```python
async def test_is_super_admin_still_true_for_real_super_admin(
    existing_super_admin: PlatformUser,
) -> None:
    got = await _scalar("SELECT is_super_admin(:u)", u=str(existing_super_admin.id))
    assert got is True


async def test_is_super_admin_false_for_unknown() -> None:
    assert await _scalar("SELECT is_super_admin(:u)", u=str(uuid4())) is False


async def test_owner_admin_member_helpers_behaviour_preserved(
    rls_as: RlsAs,
) -> None:
    """Ephemeral tenant + 4 system workspace roles already exist per-tenant
    only if the tenant existed at 0006; here we create an ephemeral tenant,
    its 4 workspace system roles, an ephemeral user, grant 'admin', and assert
    the delegated helpers match the documented truth table — then tear down."""
    uid = uuid4()
    tid = uuid4()
    email = f"x-{uid.hex[:8]}@example.com"
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": email},
        )
        await priv.execute(
            text(
                "INSERT INTO tenants (id, slug, name, created_by) "
                "VALUES (:t, :s, :n, :id)"
            ),
            {"t": str(tid), "s": f"xt-{tid.hex[:8]}", "n": "P2 RLS probe", "id": str(uid)},
        )
        # 4 workspace system roles for this ephemeral tenant + reconcile perms.
        await priv.execute(
            text(
                "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
                "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
                "('owner'),('admin'),('editor'),('read_only')) AS v(key)"
            ),
            {"t": str(tid)},
        )
        await priv.commit()
    try:
        from xtrusio_api.rbac.reconcile import reconcile_rbac

        async with SessionLocal() as s:
            await reconcile_rbac(s)  # wires role_permissions for the new roles
        async with SessionLocal() as priv:
            await priv.execute(
                text(
                    "INSERT INTO user_roles (auth_user_id, role_id, workspace_id) "
                    "SELECT :u, r.id, :t FROM roles r "
                    "WHERE r.scope='workspace' AND r.workspace_id=:t AND r.key='admin'"
                ),
                {"u": str(uid), "t": str(tid)},
            )
            await priv.commit()
        # workspace 'admin' → is_tenant_owner_or_admin TRUE, is_tenant_member TRUE
        assert await _scalar("SELECT is_tenant_owner_or_admin(:u,:t)", u=str(uid), t=str(tid)) is True
        assert await _scalar("SELECT is_tenant_member(:u,:t)", u=str(uid), t=str(tid)) is True
        # not a platform super_admin
        assert await _scalar("SELECT is_super_admin(:u)", u=str(uid)) is False
        # a different random workspace → all false
        assert (
            await _scalar("SELECT is_tenant_member(:u,:t)", u=str(uid), t=str(uuid4()))
            is False
        )
    finally:
        async with SessionLocal() as priv:
            # FK-safe teardown: user_roles → roles → tenants → auth.users.
            await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
            await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()
```

- [ ] **Step 2: Run — expect FAIL** (`is_super_admin` still reads the enum; the new behaviour-table assertions need the rewritten bodies). Run the file `-v`; the delegation tests fail.

- [ ] **Step 3: Extend `upgrade()` — replace the "Helpers + policies: Tasks 2 & 3" line with the helper rewrites:**

```python
    # Supersede the 0003 enum helpers with TRANSITION-SAFE bodies: the new
    # resolver OR the original 0003 enum check. Same signatures → every
    # existing 0003/0004 policy keeps working unchanged. The OR-legacy
    # disjunct is mandatory (spec §5, corrected): pure delegation strands
    # enum-era memberships until P3 (proven: 0006 passes, pure-0007 fails) and
    # would lock newly-onboarded owners out — this superset breaks nothing
    # mid-flight (§7.5) while giving instant-revoke for RBAC-granted access.
    # SECURITY DEFINER → the legacy EXISTS subqueries don't recurse (0003
    # technique). P3 retires the legacy disjunct when user_roles is authoritative.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_super_admin(uid uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT has_platform_perm(uid, 'platform.roles.manage')
                OR EXISTS (
                    SELECT 1 FROM platform_users
                    WHERE id = uid AND role = 'super_admin' AND is_active
                )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_owner_or_admin(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT has_workspace_perm(uid, tid, 'workspace.members.manage')
                OR EXISTS (
                    SELECT 1 FROM tenant_memberships
                    WHERE user_id = uid AND tenant_id = tid
                      AND role IN ('owner','admin')
                )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_member(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                    SELECT 1 FROM user_roles
                    WHERE auth_user_id = uid AND workspace_id = tid
                )
                OR EXISTS (
                    SELECT 1 FROM tenant_memberships
                    WHERE user_id = uid AND tenant_id = tid
                )
        $$
        """
    )

    # Policies: Task 3 adds BELOW THIS LINE (same upgrade()).
```

In `downgrade()`, **above** the function-drop lines from Task 1, add the verbatim `0003` bodies so a downgrade restores exact `0003` behaviour (the resolvers are dropped after, so these must not reference them):

```python
    # Restore the original 0003 enum-reading helper bodies.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_super_admin(uid uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM platform_users
                WHERE id = uid AND role = 'super_admin' AND is_active
            )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_owner_or_admin(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM tenant_memberships
                WHERE user_id = uid AND tenant_id = tid AND role IN ('owner','admin')
            )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_member(uid uuid, tid uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM tenant_memberships
                WHERE user_id = uid AND tenant_id = tid
            )
        $$
        """
    )
```

(Order in `downgrade()`: restore-`0003`-helper-bodies FIRST, then the Task-3 policy restores, then the Task-1 `DROP FUNCTION` resolver lines LAST — a helper must not reference a resolver that's already dropped.)

- [ ] **Step 4: Cycle + test**

```bash
make migrate-down && make migrate
uv run --directory apps/api pytest tests/rls/test_permission_engine_rls.py -v
```
Expected: all delegation tests PASS; `existing_super_admin` still `is_super_admin=true`. Also run the full pre-existing RLS suite to prove the ~13 untouched policies still behave:
`uv run --directory apps/api pytest tests/rls/ -v` → green except nothing new (the other rls test files exercise policies that call the now-delegated helpers — they must still pass identically because the truth sets are preserved).

- [ ] **Step 5: Commit**

```bash
git add apps/api/migrations/versions/0007_rls_permission_engine.py apps/api/tests/rls/test_permission_engine_rls.py
git commit -m "feat(db): 0007 delegate 0003 enum helpers to the perm resolvers (behaviour-preserving)"
```

---

### Task 3: Replace `0006` interim RBAC-table policies with perm-aware ones

**Files:**
- Modify: `apps/api/migrations/versions/0007_rls_permission_engine.py` (extend `upgrade()` + `downgrade()`)
- Modify: `apps/api/tests/rls/test_permission_engine_rls.py` (append RBAC-table policy matrix)

- [ ] **Step 1: Append the failing tests**

```python
async def test_super_admin_can_select_platform_roles(
    rls_as: RlsAs, existing_super_admin: PlatformUser
) -> None:
    async with rls_as(existing_super_admin.id) as s:
        n = (
            await s.execute(
                text("SELECT count(*) FROM roles WHERE scope='platform'")
            )
        ).scalar_one()
    assert n >= 2  # super_admin + admin system roles visible to a roles.manage holder


async def test_stranger_cannot_select_platform_roles(rls_as: RlsAs) -> None:
    uid = uuid4()
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": f"x-{uid.hex[:8]}@example.com"},
        )
        await priv.commit()
    try:
        async with rls_as(uid) as s:
            n = (
                await s.execute(
                    text("SELECT count(*) FROM roles WHERE scope='platform'")
                )
            ).scalar_one()
        assert n == 0  # no platform.roles.manage → RLS hides every platform role
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


async def test_user_sees_only_own_user_roles_rows(rls_as: RlsAs) -> None:
    uid = uuid4()
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": f"x-{uid.hex[:8]}@example.com"},
        )
        await priv.commit()
    try:
        async with rls_as(uid) as s:
            # stranger has zero grants and is no RBAC manager → sees no rows,
            # in particular NOT the real super_admin's platform grant.
            n = (await s.execute(text("SELECT count(*) FROM user_roles"))).scalar_one()
        assert n == 0
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


async def test_audit_log_hidden_from_non_auditor(rls_as: RlsAs) -> None:
    uid = uuid4()
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": f"x-{uid.hex[:8]}@example.com"},
        )
        await priv.commit()
    try:
        async with rls_as(uid) as s:
            n = (
                await s.execute(text("SELECT count(*) FROM rbac_audit_log"))
            ).scalar_one()
        assert n == 0
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


# --- direct resolver matrix (closes the P2-Task-1 review coverage gap:
# has_workspace_perm + can_manage_role + cross-scope isolation + a
# genuinely-deprecated-but-PRESENT permission). Ephemeral graph, finally-torn.

async def _make_workspace_principal() -> tuple[UUID, UUID]:
    """Ephemeral @example.com user + tenant + its 4 system workspace roles
    (perms wired via reconcile) + an 'owner' grant. Caller MUST teardown."""
    uid, tid = uuid4(), uuid4()
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, "
                "encrypted_password, email_confirmed_at, created_at, updated_at) VALUES "
                "(:id,'00000000-0000-0000-0000-000000000000','authenticated',"
                "'authenticated',:e,'',now(),now(),now())"
            ),
            {"id": str(uid), "e": f"x-{uid.hex[:8]}@example.com"},
        )
        await priv.execute(
            text(
                "INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:id)"
            ),
            {"t": str(tid), "s": f"xt-{tid.hex[:8]}", "n": "P2 resolver probe", "id": str(uid)},
        )
        await priv.execute(
            text(
                "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
                "SELECT 'workspace', :t, v.key, v.key, '', true FROM (VALUES "
                "('owner'),('admin'),('editor'),('read_only')) AS v(key)"
            ),
            {"t": str(tid)},
        )
        await priv.commit()
    from xtrusio_api.rbac.reconcile import reconcile_rbac

    async with SessionLocal() as s:
        await reconcile_rbac(s)
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO user_roles (auth_user_id, role_id, workspace_id) "
                "SELECT :u, r.id, :t FROM roles r "
                "WHERE r.scope='workspace' AND r.workspace_id=:t AND r.key='owner'"
            ),
            {"u": str(uid), "t": str(tid)},
        )
        await priv.commit()
    return uid, tid


async def _teardown_workspace_principal(uid: UUID, tid: UUID) -> None:
    async with SessionLocal() as priv:
        await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
        await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
        await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
        await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
        await priv.commit()


async def test_has_workspace_perm_and_can_manage_role_direct() -> None:
    uid, tid = await _make_workspace_principal()
    try:
        # owner has every workspace perm incl. roles.manage
        assert await _scalar(
            "SELECT has_workspace_perm(:u,:t,'workspace.roles.manage')", u=str(uid), t=str(tid)
        ) is True
        assert await _scalar(
            "SELECT has_workspace_perm(:u,:t,'workspace.members.read')", u=str(uid), t=str(tid)
        ) is True
        # can_manage_role true for that workspace's 'owner' role row
        rid = await _scalar(
            "SELECT id FROM roles WHERE scope='workspace' AND workspace_id=:t AND key='owner'",
            t=str(tid),
        )
        assert await _scalar("SELECT can_manage_role(:u,:r)", u=str(uid), r=str(rid)) is True
    finally:
        await _teardown_workspace_principal(uid, tid)


async def test_cross_scope_isolation(existing_super_admin: PlatformUser) -> None:
    uid, tid = await _make_workspace_principal()
    try:
        # workspace grant must NOT satisfy a platform check...
        assert await _scalar(
            "SELECT has_platform_perm(:u,'platform.roles.manage')", u=str(uid)
        ) is False
        # ...and the real platform super_admin must NOT satisfy a workspace
        # check for an unrelated workspace.
        assert await _scalar(
            "SELECT has_workspace_perm(:u,:t,'workspace.roles.manage')",
            u=str(existing_super_admin.id), t=str(tid),
        ) is False
    finally:
        await _teardown_workspace_principal(uid, tid)


async def test_genuinely_deprecated_present_permission_does_not_grant() -> None:
    """A permission row that EXISTS but is_deprecated=true, attached to a role
    the user holds, must NOT grant (covers the `NOT p.is_deprecated` branch —
    distinct from the unknown-key path in Task 1's test)."""
    uid, tid = await _make_workspace_principal()
    dep_key = f"workspace.zz_dep_{uid.hex[:8]}"
    try:
        async with SessionLocal() as priv:
            await priv.execute(
                text(
                    "INSERT INTO permissions (scope,key,category,description,is_deprecated) "
                    "VALUES ('workspace',:k,'Deprecated','x',true)"
                ),
                {"k": dep_key},
            )
            await priv.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM roles r, permissions p "
                    "WHERE r.scope='workspace' AND r.workspace_id=:t AND r.key='owner' "
                    "AND p.key=:k"
                ),
                {"t": str(tid), "k": dep_key},
            )
            await priv.commit()
        assert await _scalar(
            "SELECT has_workspace_perm(:u,:t,:k)", u=str(uid), t=str(tid), k=dep_key
        ) is False
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM permissions WHERE key=:k"), {"k": dep_key})
            await priv.commit()
        await _teardown_workspace_principal(uid, tid)
```

`UUID` is used by the helper signatures above, so Task 3's append re-introduces the `from uuid import UUID, uuid4` form (Task 1 had trimmed `UUID`); update the import line accordingly when appending.

- [ ] **Step 2: Run — expect FAIL** (`0006`'s `USING(true)` still lets the stranger see all `roles`/`user_roles`; `rbac_audit_log` count works differently). Run `-v`; the new tests fail.

- [ ] **Step 3: Extend `upgrade()` — replace the "Policies: Task 3" line with:**

```python
    # Replace 0006's permissive interim RBAC-table SELECT policies with
    # resolver-gated ones (removes the cross-tenant user_roles over-read the
    # P1 review flagged). Writes still go through the owner backend conn
    # (RLS does not constrain it) — no write policies needed for authenticated.
    op.execute("DROP POLICY IF EXISTS permissions_authenticated_read ON permissions")
    op.execute("DROP POLICY IF EXISTS roles_authenticated_read ON roles")
    op.execute(
        "DROP POLICY IF EXISTS role_permissions_authenticated_read ON role_permissions"
    )
    op.execute("DROP POLICY IF EXISTS user_roles_authenticated_read ON user_roles")
    op.execute("DROP POLICY IF EXISTS rbac_audit_log_no_read ON rbac_audit_log")

    # permissions: the catalog is non-sensitive key metadata; any authenticated
    # user may read it (unchanged from 0006 intent).
    op.execute(
        "CREATE POLICY permissions_read ON permissions "
        "FOR SELECT TO authenticated USING (true)"
    )
    # roles: visible to whoever may manage roles in that scope/workspace.
    op.execute(
        """
        CREATE POLICY roles_read ON roles
            FOR SELECT TO authenticated
            USING (
                (scope = 'platform'
                    AND has_platform_perm(auth.uid(), 'platform.roles.manage'))
             OR (scope = 'workspace'
                    AND has_workspace_perm(auth.uid(), workspace_id, 'workspace.roles.manage'))
            )
        """
    )
    # role_permissions: gated via can_manage_role (SECURITY DEFINER → no
    # roles-RLS recursion in the subquery).
    op.execute(
        "CREATE POLICY role_permissions_read ON role_permissions "
        "FOR SELECT TO authenticated USING (can_manage_role(auth.uid(), role_id))"
    )
    # user_roles: a user always sees their OWN grants; RBAC managers see grants
    # in the scope/workspace they manage. (No blanket read.)
    op.execute(
        """
        CREATE POLICY user_roles_read ON user_roles
            FOR SELECT TO authenticated
            USING (
                auth_user_id = auth.uid()
             OR (workspace_id IS NULL
                    AND has_platform_perm(auth.uid(), 'platform.roles.manage'))
             OR (workspace_id IS NOT NULL
                    AND has_workspace_perm(auth.uid(), workspace_id, 'workspace.roles.manage'))
            )
        """
    )
    # rbac_audit_log: scope-appropriate audit-read permission.
    op.execute(
        """
        CREATE POLICY rbac_audit_log_read ON rbac_audit_log
            FOR SELECT TO authenticated
            USING (
                (scope = 'platform'
                    AND has_platform_perm(auth.uid(), 'platform.audit.read'))
             OR (scope = 'workspace'
                    AND has_workspace_perm(auth.uid(), workspace_id, 'workspace.audit.read'))
            )
        """
    )
```

In `downgrade()`, **above** the restore-`0003`-helper block (so order is: restore-0006-policies → restore-0003-helpers → drop resolvers), add the verbatim `0006` interim policy restoration:

```python
    # Restore 0006's interim RBAC-table policies verbatim.
    op.execute("DROP POLICY IF EXISTS rbac_audit_log_read ON rbac_audit_log")
    op.execute("DROP POLICY IF EXISTS user_roles_read ON user_roles")
    op.execute("DROP POLICY IF EXISTS role_permissions_read ON role_permissions")
    op.execute("DROP POLICY IF EXISTS roles_read ON roles")
    op.execute("DROP POLICY IF EXISTS permissions_read ON permissions")
    op.execute(
        "CREATE POLICY permissions_authenticated_read ON permissions "
        "FOR SELECT TO authenticated USING (true)"
    )
    op.execute(
        "CREATE POLICY roles_authenticated_read ON roles "
        "FOR SELECT TO authenticated USING (true)"
    )
    op.execute(
        "CREATE POLICY role_permissions_authenticated_read ON role_permissions "
        "FOR SELECT TO authenticated USING (true)"
    )
    op.execute(
        "CREATE POLICY user_roles_authenticated_read ON user_roles "
        "FOR SELECT TO authenticated USING (true)"
    )
    op.execute(
        "CREATE POLICY rbac_audit_log_no_read ON rbac_audit_log "
        "FOR SELECT TO authenticated USING (false)"
    )
```

- [ ] **Step 4: Cycle + full RLS + lint/type**

```bash
make migrate-down && uv run --directory apps/api alembic current   # 0006
make migrate                                                       # 0007
uv run --directory apps/api pytest tests/rls/ -v
uv run ruff check apps/api && uv run mypy --strict apps/api/src
```
Expected: the whole `tests/rls/` suite green (the new matrix + the pre-existing files — the latter prove the delegated helpers preserved every existing policy's behaviour). Zero new ruff/mypy.

- [ ] **Step 5: Commit**

```bash
git add apps/api/migrations/versions/0007_rls_permission_engine.py apps/api/tests/rls/test_permission_engine_rls.py
git commit -m "feat(db): 0007 perm-aware RBAC-table RLS policies (replace 0006 interim)"
```

---

### Task 3b: Supersede the stale P1 interim-policy test

**Context (found by the Task-4 gate):** P1 added `tests/rbac/test_migration_0006.py::test_interim_rls_policies_present` asserting the 5 *interim* policy names (`permissions_authenticated_read`, `roles_authenticated_read`, `role_permissions_authenticated_read`, `user_roles_authenticated_read`, `rbac_audit_log_no_read`) exist. P2 Task 3 **deliberately drops those and creates perm-aware replacements** (`permissions_read`, `roles_read`, `role_permissions_read`, `user_roles_read`, `rbac_audit_log_read`). So at head `0007` that P1 test fails — it guards a posture P2 intentionally retired. Fix: remove the obsolete assertion from the P1 migration-0006 test file and add a stronger forward assertion to P2's own test file (this is not "deleting a failing test" — the asserted state no longer exists by design, and we add better coverage for the new reality).

**Files:**
- Modify: `apps/api/tests/rbac/test_migration_0006.py` (remove `test_interim_rls_policies_present`)
- Modify: `apps/api/tests/rls/test_permission_engine_rls.py` (add `test_rbac_table_perm_aware_policies_present`)

- [ ] **Step 1: Remove the obsolete test**

Delete the entire `async def test_interim_rls_policies_present() -> None:` function (and its docstring/body) from `apps/api/tests/rbac/test_migration_0006.py`. Remove any import that becomes unused as a result (only if genuinely unused — `SessionLocal`/`text` are used by other tests in that file, so likely no import change).

- [ ] **Step 2: Add the forward assertion to P2's test file**

Append to `apps/api/tests/rls/test_permission_engine_rls.py`:

```python
async def test_rbac_table_perm_aware_policies_present() -> None:
    """P2 replaced 0006's interim `*_authenticated_read`/`rbac_audit_log_no_read`
    policies with perm-aware ones. Assert the new posture and that the interim
    names are gone (the inverse of the retired P1 hardening test)."""
    new_names = {
        "permissions_read",
        "roles_read",
        "role_permissions_read",
        "user_roles_read",
        "rbac_audit_log_read",
    }
    old_names = {
        "permissions_authenticated_read",
        "roles_authenticated_read",
        "role_permissions_authenticated_read",
        "user_roles_authenticated_read",
        "rbac_audit_log_no_read",
    }
    async with SessionLocal() as s:
        rows = dict(
            (
                await s.execute(
                    text(
                        "SELECT policyname, qual FROM pg_policies "
                        "WHERE schemaname='public' AND tablename IN "
                        "('permissions','roles','role_permissions','user_roles',"
                        "'rbac_audit_log')"
                    )
                )
            ).all()
        )
    present = set(rows)
    assert new_names <= present, f"missing perm-aware policies: {new_names - present}"
    assert not (old_names & present), f"interim policies not retired: {old_names & present}"
    # audit-log is now permission-gated, NOT a blanket USING(false).
    aud = (rows.get("rbac_audit_log_read") or "").lower()
    assert "audit.read" in aud and "false" != aud.strip()
```

- [ ] **Step 3: Verify**

```bash
uv run --directory apps/api pytest tests/rls/test_permission_engine_rls.py tests/rbac/test_migration_0006.py -v
uv run --directory apps/api pytest tests/ -q
```
Expected: `test_rbac_table_perm_aware_policies_present` passes; `test_migration_0006.py` green (its other 0006-durable assertions unaffected by 0007); FULL backend suite green EXCEPT only the 2 documented `test_signup` env-failures (zero others — in particular the previously-failing `test_interim_rls_policies_present` is gone). `uv run ruff check apps/api` + `uv run mypy --strict apps/api/src` zero new vs baseline.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/rbac/test_migration_0006.py apps/api/tests/rls/test_permission_engine_rls.py
git commit -m "test(rbac): supersede stale P1 interim-policy test with P2 perm-aware-policy assertion"
```

---

### Task 4: Whole-phase gate

**Files:** none (verification only)

- [ ] **Step 1: Full reversibility round-trip**

```bash
make migrate-down && uv run --directory apps/api alembic current   # 0006
make migrate && uv run --directory apps/api alembic current        # 0007
```
Then read-only confirm at `0006` (mid-downgrade state) the `0003` helper bodies are the enum versions and the `0006` interim policies exist (a downgrade test inside the suite already asserts behaviour; record the alembic transitions here).

- [ ] **Step 2: Full backend suite**

```bash
uv run --directory apps/api pytest tests/ -v
```
Expected: green EXCEPT the 2 documented env-failures (`test_signup_status_default_false`, `test_signup_disabled_returns_403`) — zero NEW failures. The `tests/rls/*` (old + new), `tests/rbac/*`, route/integration tests all pass (the delegated helpers keep every enum-era policy behaving identically; nothing in the backend reads the resolvers yet — that's P3).

- [ ] **Step 3: Lint/type + single head**

```bash
uv run ruff check apps/api && uv run mypy --strict apps/api/src
uv run --directory apps/api alembic heads   # exactly one head: 0007
```
Expected: only the accepted pre-existing baseline; single head `0007`.

- [ ] **Step 4: No commit.** Report results to the controller.

---

## Self-Review (completed during planning)

**Spec coverage (§5/§6/§10 row P2):**
- §5 `has_platform_perm`/`has_workspace_perm` SECURITY DEFINER resolvers, single source of truth, RLS-recursion-safe → Task 1.
- §5/§10 supersede the `0003` `is_super_admin`/`is_tenant_owner_or_admin`/`is_tenant_member` helpers by delegating (every existing policy keeps working, now table-sourced → instant revocation) → Task 2; behaviour-preservation proven via the documented truth-table mapping + the pre-existing `tests/rls/` suite staying green.
- §5/§6 replace `0006`'s permissive interim RBAC-table policies with perm-aware SELECT policies (removes the P1-flagged cross-tenant `user_roles` over-read; audit-log gated by `*.audit.read`) → Task 3.
- §10 "full RLS test matrix" → resolver correctness + delegation behaviour-preservation + RBAC-table policy matrix in `test_permission_engine_rls.py` + the untouched pre-existing `tests/rls/` files as the regression guard for the ~13 delegated-helper policies.
- §11 reversible (downgrade restores `0003` helper bodies + `0006` policies verbatim, ordered so no helper references a dropped resolver), single Alembic head `0007`, pure raw SQL, test-data hygiene (ephemeral `@example.com` + `finally` teardown; real super_admin read-only).

**Out of P2 scope (correctly deferred):** backend `require_permission()` / `/me` effective perms / invite-acceptance→`user_roles` / audit writes / dropping enum columns / privilege-escalation guard enforcement (all P3); admin UIs (P4/P5). P2 changes ONLY the DB layer + tests; zero Python source change.

**Placeholder scan:** none — every SQL fn/policy and every test body is complete and concrete. The "Tasks 2 & 3 add below/above" comment lines are explicit assembly markers (same technique P1 used), each replaced by fully-specified SQL in its task.

**Type/name consistency:** resolver names `has_platform_perm(uuid,text)` / `has_workspace_perm(uuid,uuid,text)` / `can_manage_role(uuid,uuid)` consistent across migration + tests; helper signatures unchanged from `0003` (so `0003`/`0004` policy SQL is untouched — verified against the grep of policies referencing them); `_scalar`/`_scalar_all` test helpers defined before use; downgrade ordering (restore 0006 policies → restore 0003 helper bodies → drop resolvers) prevents dangling references.

**Risk note for the spec-compliance reviewer:** behaviour-preservation rests on the
**transition-safe `resolver OR 0003-enum` superset** (NOT pure delegation — pure delegation was
proven to break onboarding/the pre-RBAC RLS suite; spec §5 was corrected 2026-05-17). The hard
acceptance gate: the **entire pre-existing `tests/rls/` suite (test_tenants_rls,
test_tenant_memberships_rls, test_platform_invites_rls, test_tenant_invites_rls,
test_platform_settings_rls) must be 100% GREEN at `0007`** — in particular
`test_tenants_rls::test_member_sees_only_their_tenants` and
`test_tenant_invites_rls::test_editor_cannot_see_invites`, which a pure-delegation `0007` turns
red and a correct transition-safe `0007` keeps green (verify by running the full suite, and
`make migrate-down` → those + everything still green at `0006`, → `make migrate` → still green at
`0007`). The reviewer must also confirm `make migrate-down` restores the exact `0006`
policy/helper set and that P3-retires-legacy-disjunct is recorded as a carry-forward.
