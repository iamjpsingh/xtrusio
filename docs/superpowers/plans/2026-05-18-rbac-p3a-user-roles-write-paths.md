# RBAC P3a — `user_roles` Write-Paths & Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every principal-creating write path (onboarding, platform/tenant invite-acceptance, bootstrap) ALSO write the equivalent `user_roles` grant, and add an idempotent reconciler that backfills any enum-era `platform_users`/`tenant_memberships` rows lacking a grant — so that **every** principal resolves through `has_*_perm` before P3b flips enforcement to the resolvers. **Zero authorization-behaviour change** (enum checks still in force; this only *adds* `user_roles` rows).

**Architecture:** A single reusable idempotent `grant_role()` helper (resolve the `roles` row by `(scope, key[, workspace_id])`, INSERT `user_roles` with `ON CONFLICT DO NOTHING` against the existing `UNIQUE(auth_user_id, role_id, workspace_id)`) is called from the 4 write paths. A `reconcile_user_roles_from_enums()` function projects existing enum rows → `user_roles` (idempotent; same enum→system-role mapping P1's `0006` backfill used), wired into the existing app-startup reconcile hook + a `make` target. No enforcement/route/`/me` change (that is P3b). No enum-column drop or helper-disjunct retirement (that is P3c).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, asyncpg, Postgres (Supabase managed), pytest + pytest-asyncio, `uv`, `make`.

**Spec:** `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` §5/§8/§10 (P3). **Builds on merged P2** (`main`: migration `0007` resolvers + transition-safe helpers; `rbac/catalog.py`; `rbac/reconcile.py`; the single-super_admin partial unique index `user_roles_one_super_admin` on fixed role id `00000000-0000-0000-0000-0000000000a1`). This is the **P3a** slice; P3b (enforcement conversion + `/me` effective perms) and P3c (audit + governance + `0008` enum-disjunct retirement) are separate later plans.

---

## Conventions that apply to EVERY task (read once)

- Branch `rbac-p3-backend-enforcement` (already cut from merged `main`). Do NOT switch branches.
- Backend tests: `uv run --directory apps/api pytest <path> -v`. Async DB test modules: `pytestmark = pytest.mark.asyncio(loop_scope="session")`.
- **Test-data hygiene (mandatory):** never create/grant a `super_admin` in a test (P1 `user_roles_one_super_admin` partial unique index + `tests/test_no_super_admin_creation.py` guard forbid it — and that guard greps for `INSERT INTO user_roles … super_admin`, so do NOT write such SQL in tests). Positive super_admin facts use the read-only `existing_super_admin` fixture. Other principals are ephemeral `@example.com` `auth.users` rows created in a privileged `SessionLocal()` and deleted FK-safe in a `finally:` (mirror `apps/api/tests/rls/test_permission_engine_rls.py`). No `@example.com` row survives a test.
- Backend connects as owner (RLS does not constrain it — `core/db.py`); `user_roles` writes are unrestricted, so correctness is purely the Python logic + the DB UNIQUE/partial-unique constraints.
- Lint/type before commit: `uv run ruff check apps/api` + `uv run mypy --strict apps/api/src` — zero NEW errors. Accepted pre-existing baseline: 4 ruff `I001` (`scripts/bootstrap.py`, `services/{signup,platform_invites,tenant_invites}.py`); 1 `jose` mypy in `core/auth.py`.
- Accepted pre-existing env-failures (do NOT "fix"): `tests/routes/test_signup.py::test_signup_status_default_false` + `::test_signup_disabled_returns_403` (managed DB `signups_enabled=true`).
- Commit with repo git identity. **NO `Co-Authored-By` trailer.** TDD order. **No migration in P3a** (Alembic head stays `0007`).
- **Behaviour invariant for P3a:** authorization decisions must be byte-identical before/after (enum checks unchanged). The full pre-existing suite (esp. `tests/rls/`, route authz tests, integration flows) must stay green — P3a only *adds* `user_roles` rows. If any pre-existing authz test changes outcome, STOP/BLOCKED.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/src/xtrusio_api/rbac/grants.py` | NEW. `grant_role(db, *, auth_user_id, scope, key, workspace_id=None, granted_by=None)` — resolve the `roles` row and INSERT an idempotent `user_roles` grant. The single reusable unit every write path + reconciler uses. |
| `apps/api/src/xtrusio_api/rbac/reconcile.py` | MODIFY. Add `wire_workspace_role_perms(db, *, workspace_id)` (SCOPED, no-commit, sets one workspace's 4 system roles' `role_permissions` per `SYSTEM_ROLE_PERMISSIONS`/`_WORKSPACE_ROLE_MAP`) + `reconcile_user_roles_from_enums(db)` (idempotent enum→`user_roles` backfill, same mapping as `0006`). |
| `apps/api/src/xtrusio_api/services/onboarding.py` | MODIFY (`create_tenant_with_owner`) — seed the new tenant's 4 workspace system roles (0006-friendly name/description), wire ONLY that workspace's `role_permissions` via the scoped helper, grant the `owner` role, all in ONE atomic `db.commit()` (NO global `reconcile_rbac` on the request path — see Task 2 rationale). |
| `apps/api/src/xtrusio_api/services/invite_acceptance.py` | MODIFY (`_accept_platform` ~line 60; `_accept_tenant` ~line 87) — also grant the mapped platform/workspace role. |
| `apps/api/src/xtrusio_api/scripts/bootstrap.py` | MODIFY (`_run`, after the `platform_users` insert ~line 597; force path ~lines 584-591) — also grant the platform `super_admin` role; force path clears its `user_roles` grant too. |
| `apps/api/src/xtrusio_api/main.py` | MODIFY — the existing startup reconcile hook also calls `reconcile_user_roles_from_enums`. |
| `Makefile` | MODIFY — `rbac-seed` target (or a sibling) also runs the enum→user_roles reconcile. |
| `apps/api/tests/rbac/test_grants.py` | NEW. `grant_role` resolution + idempotency. |
| `apps/api/tests/rbac/test_reconcile_user_roles.py` | NEW. enum→user_roles backfill correctness + idempotency (read-only vs `existing_super_admin`; ephemeral for the rest). |
| `apps/api/tests/services/test_onboarding_grants.py`, `apps/api/tests/services/test_invite_acceptance_grants.py` | NEW. write-path grant assertions. |
| `apps/api/tests/scripts/test_bootstrap_grant.py` | NEW. bootstrap grant assertion (no super_admin creation — see Task 5 approach). |

---

### Task 1: `grant_role()` idempotent helper

**Files:**
- Create: `apps/api/src/xtrusio_api/rbac/grants.py`
- Test: `apps/api/tests/rbac/test_grants.py`

- [ ] **Step 1: Write the failing test**

`apps/api/tests/rbac/test_grants.py`:

```python
"""grant_role(): resolve a roles row by (scope,key[,workspace_id]) and insert
an idempotent user_roles grant. Ephemeral @example.com user + tenant + system
roles (reconcile wires perms), FK-safe finally teardown. No super_admin."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.rbac.grants import grant_role

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_grant_role_workspace_is_idempotent() -> None:
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
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:s,:n,:id)"),
            {"t": str(tid), "s": f"xt-{tid.hex[:8]}", "n": "P3a grant probe", "id": str(uid)},
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
    try:
        async with SessionLocal() as s:
            await grant_role(s, auth_user_id=uid, scope="workspace", key="owner",
                             workspace_id=tid)
            await s.commit()
        async with SessionLocal() as s:  # second call = no duplicate row
            await grant_role(s, auth_user_id=uid, scope="workspace", key="owner",
                             workspace_id=tid)
            await s.commit()
        async with SessionLocal() as s:
            n = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                        "WHERE ur.auth_user_id=:u AND r.scope='workspace' "
                        "AND r.workspace_id=:t AND r.key='owner'"
                    ),
                    {"u": str(uid), "t": str(tid)},
                )
            ).scalar_one()
        assert n == 1
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
            await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()


async def test_grant_role_unknown_role_raises() -> None:
    async with SessionLocal() as s:
        with pytest.raises(LookupError):
            await grant_role(s, auth_user_id=uuid4(), scope="platform",
                             key="does_not_exist")
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError: xtrusio_api.rbac.grants`):
`uv run --directory apps/api pytest tests/rbac/test_grants.py -v`

- [ ] **Step 3: Implement** `apps/api/src/xtrusio_api/rbac/grants.py`:

```python
"""Idempotent user_roles grant helper — the single write path for granting a
role to a principal. Resolves the roles row by (scope, key[, workspace_id])
and inserts user_roles with ON CONFLICT DO NOTHING against the
UNIQUE(auth_user_id, role_id, workspace_id) constraint. Used by onboarding,
invite-acceptance, bootstrap, and the enum→user_roles reconciler.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def grant_role(
    db: AsyncSession,
    *,
    auth_user_id: UUID,
    scope: str,
    key: str,
    workspace_id: UUID | None = None,
    granted_by: UUID | None = None,
) -> None:
    """Grant the (scope, key[, workspace_id]) system role to auth_user_id.

    Idempotent: a duplicate (auth_user_id, role_id, workspace_id) is a no-op.
    Raises LookupError if no matching is_system role exists (caller bug /
    unmapped enum value — must be handled explicitly, never silently).
    The caller owns the surrounding transaction (no commit here).
    """
    role_id = (
        await db.execute(
            text(
                "SELECT id FROM roles "
                "WHERE scope = :scope AND key = :key AND is_system "
                "AND workspace_id IS NOT DISTINCT FROM :wid"
            ),
            {"scope": scope, "key": key, "wid": workspace_id},
        )
    ).scalar_one_or_none()
    if role_id is None:
        raise LookupError(
            f"no is_system role for scope={scope!r} key={key!r} "
            f"workspace_id={workspace_id!r}"
        )
    await db.execute(
        text(
            "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
            "VALUES (:u, :r, :w, :g) "
            "ON CONFLICT (auth_user_id, role_id, workspace_id) DO NOTHING"
        ),
        {"u": auth_user_id, "r": role_id, "w": workspace_id, "g": granted_by},
    )
```

- [ ] **Step 4: Run — expect PASS** (2 passed): `uv run --directory apps/api pytest tests/rbac/test_grants.py -v`

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check apps/api && uv run mypy --strict apps/api/src
git add apps/api/src/xtrusio_api/rbac/grants.py apps/api/tests/rbac/test_grants.py
git commit -m "feat(rbac): idempotent grant_role() helper (resolve role + insert user_roles)"
```

---

### Task 2: onboarding also grants the workspace `owner` role

**Files:**
- Modify: `apps/api/src/xtrusio_api/services/onboarding.py` (`create_tenant_with_owner`)
- Test: `apps/api/tests/services/test_onboarding_grants.py`

- [ ] **Step 1: Read** `apps/api/src/xtrusio_api/services/onboarding.py` fully. Confirm `create_tenant_with_owner` creates the `Tenant` (flushed → `tenant.id`), then `db.add(TenantMembership(tenant_id=tenant.id, user_id=user_id, role=TenantRole.OWNER))`, then `await db.commit()`. **Critical:** migration `0006` only seeds the 4 workspace system roles for tenants that existed at migrate time; a brand-new tenant created here has NO `roles` rows yet, so `grant_role(scope='workspace', key='owner', workspace_id=tenant.id)` would `LookupError`. Onboarding must first seed this tenant's 4 workspace system roles + their `role_permissions` (reuse `reconcile_rbac`'s per-workspace wiring) BEFORE granting. Inspect `apps/api/src/xtrusio_api/rbac/reconcile.py` to confirm `reconcile_rbac(db)` (re)wires workspace system roles for ALL tenants idempotently — calling it after the tenant is flushed seeds the new tenant's roles. (If `reconcile_rbac` only wires `role_permissions` for *existing* role rows and does NOT create the per-tenant role rows, the onboarding path must INSERT the 4 workspace system role rows for `tenant.id` first — verify which, and follow whatever `0006`'s seed SQL did: `INSERT INTO roles (scope,workspace_id,key,name,description,is_system) SELECT 'workspace', :tid, v.key, v.key, '', true FROM (VALUES ('owner'),('admin'),('editor'),('read_only')) v(key)`.)

- [ ] **Step 2: Write the failing test** `apps/api/tests/services/test_onboarding_grants.py`:

```python
"""Onboarding also creates a user_roles 'owner' grant for the new workspace,
in addition to the existing tenant_memberships(role=OWNER) row (unchanged).
Ephemeral @example.com user; FK-safe teardown."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.services.onboarding import create_tenant_with_owner

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_onboarding_grants_owner_user_role() -> None:
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
    tid = None
    try:
        async with SessionLocal() as s:
            tenant = await create_tenant_with_owner(
                s, user_id=uid, workspace_name="P3a Onboard Probe"
            )
            tid = tenant.id
        async with SessionLocal() as s:
            # legacy enum row STILL written (behaviour unchanged)
            m = (
                await s.execute(
                    text(
                        "SELECT role::text FROM tenant_memberships "
                        "WHERE user_id=:u AND tenant_id=:t"
                    ),
                    {"u": str(uid), "t": str(tid)},
                )
            ).scalar_one()
            assert m == "owner"
            # NEW: user_roles owner grant for this workspace
            g = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
                        "WHERE ur.auth_user_id=:u AND r.scope='workspace' "
                        "AND r.workspace_id=:t AND r.key='owner'"
                    ),
                    {"u": str(uid), "t": str(tid)},
                )
            ).scalar_one()
            assert g == 1
    finally:
        async with SessionLocal() as priv:
            if tid is not None:
                await priv.execute(text("DELETE FROM user_roles WHERE auth_user_id=:u"), {"u": str(uid)})
                await priv.execute(text("DELETE FROM tenant_memberships WHERE user_id=:u"), {"u": str(uid)})
                await priv.execute(text("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE workspace_id=:t)"), {"t": str(tid)})
                await priv.execute(text("DELETE FROM roles WHERE workspace_id=:t"), {"t": str(tid)})
                await priv.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": str(tid)})
            await priv.execute(text("DELETE FROM auth.users WHERE id=:u"), {"u": str(uid)})
            await priv.commit()
```

- [ ] **Step 3: Run — expect FAIL** (`g == 0`): `uv run --directory apps/api pytest tests/services/test_onboarding_grants.py -v`

- [ ] **Step 4a: Add the scoped no-commit helper** to `apps/api/src/xtrusio_api/rbac/reconcile.py` (it already imports `text`, `AsyncSession`, `SYSTEM_ROLE_PERMISSIONS`, and defines `_WORKSPACE_ROLE_MAP = {"owner":"owner","admin":"workspace_admin","editor":"editor","read_only":"read_only"}`). Append:

```python
async def wire_workspace_role_perms(db: AsyncSession, *, workspace_id) -> None:
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
```

- [ ] **Step 4b: Implement onboarding** — in `create_tenant_with_owner`, replace the existing single `await db.commit()` with the block below (keep slug/`AlreadyHasMembershipError`/`Tenant`/`TenantMembership(...OWNER)` lines byte-unchanged ABOVE it). Add imports `from ..rbac.grants import grant_role` and `from ..rbac.reconcile import wire_workspace_role_perms`. ONE atomic commit — NO `reconcile_rbac` on the request path (it self-commits mid-op → partial-failure window + O(all-tenants) churn; the scoped helper has neither). Use 0006's friendly `(key,name,description)` tuples so new-tenant role rows match migrate-time ones:

```python
    db.add(TenantMembership(tenant_id=tenant.id, user_id=user_id, role=TenantRole.OWNER))
    await db.flush()
    # 0006 only seeded workspace system roles for tenants existing at migrate
    # time; a brand-new tenant has none. Seed its 4 system roles (0006-friendly
    # name/description), wire ONLY this workspace's role_permissions, grant the
    # owner — all in the SINGLE commit below (atomic: no partial-failure window,
    # no global all-tenants reconcile on the request path).
    await db.execute(
        text(
            "INSERT INTO roles (scope, workspace_id, key, name, description, is_system) "
            "SELECT 'workspace', :tid, v.key, v.name, v.description, true FROM (VALUES "
            "('owner','Owner','Governs the workspace; manages roles'),"
            "('admin','Admin','Operates the workspace; cannot manage roles'),"
            "('editor','Editor','Content write access'),"
            "('read_only','Read Only','View-only access')"
            ") AS v(key, name, description) ON CONFLICT DO NOTHING"
        ),
        {"tid": tenant.id},
    )
    await db.flush()
    await wire_workspace_role_perms(db, workspace_id=tenant.id)
    await grant_role(
        db, auth_user_id=user_id, scope="workspace", key="owner",
        workspace_id=tenant.id,
    )
    await db.commit()
    await db.refresh(tenant)
    return tenant
```
(Adjust to the file's exact tail — preserve whatever `db.refresh`/`return` the original had; the point is: ONE commit, scoped wiring, no `reconcile_rbac` call. Verify by the Task-2 test + the pre-existing onboarding/integration suite staying green.)

- [ ] **Step 5: Run — expect PASS**; then `uv run --directory apps/api pytest tests/routes/test_onboarding.py tests/integration/test_signup_to_tenant_flow.py -v` (pre-existing onboarding/integration tests STILL green — behaviour unchanged). `ruff`/`mypy` clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/services/onboarding.py apps/api/tests/services/test_onboarding_grants.py
git commit -m "feat(onboarding): also write user_roles owner grant + seed new workspace roles"
```

---

### Task 3: invite-acceptance also grants the mapped role (platform + tenant)

**Files:**
- Modify: `apps/api/src/xtrusio_api/services/invite_acceptance.py` (`_accept_platform`, `_accept_tenant`)
- Test: `apps/api/tests/services/test_invite_acceptance_grants.py`

- [ ] **Step 1: Read** `apps/api/src/xtrusio_api/services/invite_acceptance.py` fully. `_accept_platform` adds `PlatformUser(id=user_id, email, role=invite.role, is_active=True)` then commits; `invite.role` is `PlatformRole` ∈ {admin, super_admin} but the platform-invite schema validator rejects `super_admin`, so in practice only `admin` (and legacy `editor` which has NO platform system role — spec §2.7). `_accept_tenant` adds `TenantMembership(tenant_id=invite.tenant_id, user_id, role=invite.role)`; `invite.role` is `TenantRole` ∈ {admin, editor, read_only} and that tenant's 4 workspace system roles already exist (tenant pre-existed). Confirm the `IntegrityError → AlreadyProvisionedError` handling and that both commit once.

- [ ] **Step 2: Write the failing test** `apps/api/tests/services/test_invite_acceptance_grants.py` — two tests: (a) platform admin invite acceptance → a `user_roles` platform `admin` grant exists; (b) tenant `editor` invite acceptance → a `user_roles` workspace `editor` grant for that tenant exists. Use the established ephemeral-`@example.com` + pre-created `platform_invites`/`tenant_invites` rows pattern from `apps/api/tests/integration/test_invite_full_flow.py` (read it for the exact invite-row setup); FK-safe `finally` teardown of `user_roles`, `platform_users`/`tenant_memberships`, the invite rows, `auth.users`. Assert BOTH the legacy enum row (unchanged) AND the new `user_roles` grant. (Do NOT exercise a `super_admin` platform invite — schema rejects it and the hygiene guard forbids the SQL.)

  Write the two tests concretely against the real `_accept_platform`/`_accept_tenant` signatures observed in Step 1 (they take `db, *, user_id, email, invite_id`). Pre-insert a `platform_invites` row with `role='admin'` (and `role_id` per `0006`'s backfill — set it via the same `roles` lookup) and a `tenant_invites` row with `role='editor'` for an ephemeral tenant whose 4 workspace system roles exist (create them like Task 1). Mirror `test_invite_full_flow.py`'s invite-row columns exactly.

- [ ] **Step 3: Run — expect FAIL** (no `user_roles` grant yet).

- [ ] **Step 4: Implement.** Import `from ..rbac.grants import grant_role`. In `_accept_platform`, AFTER the `PlatformUser` add and the successful commit path, before `return`: map `invite.role` → grant. Platform: only `admin` maps (super_admin impossible here; `editor` has no platform system role → explicitly skip with a comment, do NOT raise). In `_accept_tenant`, after the `TenantMembership` add/commit: `await grant_role(db, auth_user_id=user_id, scope='workspace', key=invite.role.value, workspace_id=invite.tenant_id)`. Keep the grant inside the SAME transaction as the membership insert (move the `grant_role` call to just before the existing `await db.commit()` so the `IntegrityError→AlreadyProvisionedError` semantics still apply and a re-accept is idempotent — `grant_role` is ON CONFLICT DO NOTHING). For platform:

```python
    db.add(PlatformUser(id=user_id, email=email, role=invite.role, is_active=True))
    if invite.role.value == "admin":  # only 'admin' has a platform system role
        await grant_role(db, auth_user_id=user_id, scope="platform", key="admin")
    invite.accepted_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise AlreadyProvisionedError() from e
```
For tenant:
```python
    db.add(TenantMembership(tenant_id=invite.tenant_id, user_id=user_id, role=invite.role))
    await grant_role(db, auth_user_id=user_id, scope="workspace",
                     key=invite.role.value, workspace_id=invite.tenant_id)
    invite.accepted_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise AlreadyProvisionedError() from e
```

- [ ] **Step 5: Run — expect PASS**; then `uv run --directory apps/api pytest tests/routes/test_invite_acceptance.py tests/integration/test_invite_full_flow.py -v` (pre-existing green — behaviour unchanged). `ruff`/`mypy` clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/services/invite_acceptance.py apps/api/tests/services/test_invite_acceptance_grants.py
git commit -m "feat(invites): accept also writes the mapped user_roles grant (platform admin / workspace role)"
```

---

### Task 4: bootstrap also grants the platform `super_admin` role

**Files:**
- Modify: `apps/api/src/xtrusio_api/scripts/bootstrap.py`
- Test: `apps/api/tests/scripts/test_bootstrap_grant.py`

- [ ] **Step 1: Read** `apps/api/src/xtrusio_api/scripts/bootstrap.py` fully. `_run` checks existing `PlatformUser.role==SUPER_ADMIN`; with `force` deletes old super_admin `platform_users` + their `auth.users`; creates the Supabase auth user; `db.add(PlatformUser(id=result.user.id, email, role=SUPER_ADMIN, is_active=True))`; commit. The platform `super_admin` role has the FIXED id `00000000-0000-0000-0000-0000000000a1`; the partial unique index `user_roles_one_super_admin` allows at most ONE `user_roles` row with that role_id. So the force path MUST also delete the prior super_admin's `user_roles` grant (else the new grant violates the index). `grant_role(scope='platform', key='super_admin')` resolves that fixed-id role.

- [ ] **Step 2: Write the failing test** `apps/api/tests/scripts/test_bootstrap_grant.py`. **Hygiene constraint:** tests must NOT create a super_admin, and the no-super_admin guard greps for `INSERT INTO user_roles … super_admin`. Therefore do NOT call bootstrap in a test. Instead, assert the invariant **read-only against the existing real super_admin** (the operator-created one): it must have BOTH a `platform_users` super_admin row AND a `user_roles` grant to the fixed super_admin role id — i.e. P3a's reconcile (Task 6) + this change keep them consistent. Use the `existing_super_admin` fixture:

```python
"""Read-only: the real operator super_admin has a user_roles grant to the
fixed platform super_admin role (0000…00a1). Never creates a super_admin."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_existing_super_admin_has_user_roles_grant(
    existing_super_admin: PlatformUser,
) -> None:
    async with SessionLocal() as s:
        n = (
            await s.execute(
                text(
                    "SELECT count(*) FROM user_roles "
                    "WHERE auth_user_id=:u "
                    "AND role_id='00000000-0000-0000-0000-0000000000a1'"
                ),
                {"u": str(existing_super_admin.id)},
            )
        ).scalar_one()
    assert n == 1
```
(This already passes today via P1's `0006` backfill; it is the regression guard that bootstrap/reconcile keep it true. Bootstrap's own grant-on-create + force-cleanup is verified by code review + the operator runbook, NOT by a test that creates a super_admin.)

- [ ] **Step 3: Run — expect PASS already** (P1 backfilled it). This test is a guard, not red-first; note in the task report that it is a standing invariant assertion.

- [ ] **Step 4: Implement bootstrap changes.** Add `from xtrusio_api.rbac.grants import grant_role`. In the `force` branch, after deleting old super_admin `platform_users`/`auth.users`, also clear the stale grant:
```python
        await db.execute(
            sa_text(
                "DELETE FROM user_roles "
                "WHERE role_id='00000000-0000-0000-0000-0000000000a1'"
            )
        )
```
After `db.add(PlatformUser(id=result.user.id, email=email, role=PlatformRole.SUPER_ADMIN, is_active=True))` and its `await db.commit()`, add (own statement, then commit):
```python
    async with SessionLocal() as s2:
        await grant_role(s2, auth_user_id=result.user.id, scope="platform",
                         key="super_admin")
        await s2.commit()
```
(Use the script's existing session/commit structure; ensure the grant is committed after the platform_users row exists. The `ON CONFLICT DO NOTHING` + the force-path delete keep it idempotent and within the single-super_admin invariant.)

- [ ] **Step 5: Run** `uv run --directory apps/api pytest tests/scripts/ -v` (the guard passes) + `uv run --directory apps/api pytest tests/test_no_super_admin_creation.py -v` (the hygiene guard must still pass — confirm the new bootstrap SQL string isn't in a TEST file; it's in `scripts/bootstrap.py`, which is allowed). `ruff`/`mypy` clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/scripts/bootstrap.py apps/api/tests/scripts/test_bootstrap_grant.py
git commit -m "feat(bootstrap): also grant platform super_admin user_role; force clears stale grant"
```

---

### Task 5: `reconcile_user_roles_from_enums()` + startup/Make wiring

**Files:**
- Modify: `apps/api/src/xtrusio_api/rbac/reconcile.py`
- Modify: `apps/api/src/xtrusio_api/main.py`
- Modify: `Makefile`
- Test: `apps/api/tests/rbac/test_reconcile_user_roles.py`

- [ ] **Step 1: Read** `apps/api/src/xtrusio_api/rbac/reconcile.py` (the `reconcile_rbac` structure + single commit) and `apps/api/migrations/versions/0006_rbac_foundation.py` lines ~189-214 (the enum→user_roles backfill SQL: platform `WHERE pu.is_active AND pu.role::text IN ('super_admin','admin')`; tenant from `tenant_memberships`). The new function replays exactly that projection, idempotently (`ON CONFLICT DO NOTHING`), so any enum row created after the `0006` migration also gets its grant. Read `apps/api/src/xtrusio_api/main.py` to find the existing startup reconcile hook (it already calls `reconcile_rbac` per P1).

- [ ] **Step 2: Write the failing test** `apps/api/tests/rbac/test_reconcile_user_roles.py`: create an ephemeral `@example.com` user + ephemeral tenant + its 4 workspace system roles + a `tenant_memberships(role='admin')` row but DELETE any auto `user_roles` (simulate an enum-only post-0006 membership), call `reconcile_user_roles_from_enums(s)`, assert a `user_roles` workspace `admin` grant now exists; call again → still exactly 1 (idempotent). FK-safe `finally`. Also a read-only assertion: after reconcile, zero `tenant_memberships` rows lack a matching `user_roles` grant (`SELECT count(*) FROM tenant_memberships m LEFT JOIN roles r ON r.scope='workspace' AND r.workspace_id=m.tenant_id AND r.key=m.role::text LEFT JOIN user_roles ur ON ur.auth_user_id=m.user_id AND ur.role_id=r.id AND ur.workspace_id=m.tenant_id WHERE ur.id IS NULL` == 0). Do NOT touch super_admin.

- [ ] **Step 3: Run — expect FAIL** (`ModuleNotFoundError`/AttributeError: `reconcile_user_roles_from_enums`).

- [ ] **Step 4: Implement** — append to `apps/api/src/xtrusio_api/rbac/reconcile.py`:

```python
async def reconcile_user_roles_from_enums(db: AsyncSession) -> None:
    """Idempotently make every enum-era principal resolvable via the resolvers.

    Step A — close the role-ROW gap: any tenant onboarded AFTER 0006 but
    BEFORE P3a-Task-2 deployed has no workspace system role rows (the global
    reconcile_rbac only wires perms for EXISTING role rows, never creates per-
    tenant rows). Seed the 4 workspace system roles for EVERY tenant (0006
    shape + friendly name/desc, ON CONFLICT DO NOTHING) and wire each such
    workspace's role_permissions via the scoped wire_workspace_role_perms.
    Step B — project enum principals → user_roles (the 0006 mapping, repeatable
    for rows created since): active platform super_admin/admin → platform
    system role; every tenant_memberships row → that workspace's matching
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
    # Step B: project enum principals → user_roles.
    # The platform INSERT needs an explicit NOT EXISTS guard (not just
    # ON CONFLICT): the single-super_admin index `user_roles_one_super_admin`
    # is an EXPRESSION partial index `ON user_roles ((true)) WHERE
    # role_id='…00a1'`, which `ON CONFLICT (auth_user_id,role_id,workspace_id)`
    # cannot use as an arbiter — so re-running this in any env that already
    # has the super_admin grant would raise IntegrityError. The NOT EXISTS
    # makes it add ONLY genuinely-missing grants (idempotent for admin AND
    # super_admin); a genuinely-inconsistent cross-identity …00a1 state still
    # (correctly) fails loud rather than being masked.
    await db.execute(
        text(
            "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
            "SELECT pu.id, r.id, NULL, NULL FROM platform_users pu "
            "JOIN roles r ON r.scope='platform' AND r.workspace_id IS NULL "
            "  AND r.key = pu.role::text AND r.is_system "
            "WHERE pu.is_active AND pu.role::text IN ('super_admin','admin') "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM user_roles ux "
            "    WHERE ux.auth_user_id = pu.id AND ux.role_id = r.id "
            "      AND ux.workspace_id IS NULL"
            "  ) "
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
```
(`text` is already imported; `wire_workspace_role_perms` is defined in this same file by Task 2. Step A's role-seed runs before the wiring loop and the Step-B JOINs, so a post-0006/pre-Task-2 tenant is fully healed — closing the `_accept_tenant` `LookupError` gap the Task-3 review surfaced.)

Add to the Task-5 test (`test_reconcile_user_roles.py`): a case that creates an ephemeral tenant with a `tenant_memberships(role='admin')` row but NO workspace `roles` rows (simulating post-0006/pre-Task-2), calls `reconcile_user_roles_from_enums`, and asserts (a) the tenant now has its 4 workspace system roles, (b) a `user_roles` workspace `admin` grant exists for that member, (c) idempotent on a 2nd call. FK-safe `finally`; no super_admin.

- [ ] **Step 5: Wire startup + Make.** In `apps/api/src/xtrusio_api/main.py`, in the existing startup hook that calls `reconcile_rbac`, add a call to `reconcile_user_roles_from_enums` immediately after (same best-effort try/except that wraps the existing reconcile — boot must not fail). In `Makefile`, extend the existing `rbac-seed` recipe to also run the enum→user_roles reconcile (e.g. a second `python -m` line or extend the reconcile entrypoint to call both). Match the existing `rbac-seed`/`python -m xtrusio_api.rbac` mechanism — read the Makefile + `apps/api/src/xtrusio_api/rbac/__main__.py` and have `__main__` call both `reconcile_rbac` and `reconcile_user_roles_from_enums`.

- [ ] **Step 6: Run** `uv run --directory apps/api pytest tests/rbac/test_reconcile_user_roles.py -v` (pass) + `make rbac-seed` (prints success; idempotent on the managed DB) + `uv run --directory apps/api pytest tests/ -q` (FULL backend suite — green except ONLY the 2 documented `test_signup` env-failures; behaviour unchanged everywhere). `ruff`/`mypy` clean.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/xtrusio_api/rbac/reconcile.py apps/api/src/xtrusio_api/rbac/__main__.py apps/api/src/xtrusio_api/main.py Makefile apps/api/tests/rbac/test_reconcile_user_roles.py
git commit -m "feat(rbac): reconcile_user_roles_from_enums + startup/make wiring (backfill post-0006 enum rows)"
```

---

### Task 6: Whole-slice gate

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite**

```bash
uv run --directory apps/api pytest tests/ -q
```
Expected: green EXCEPT ONLY `tests/routes/test_signup.py::test_signup_status_default_false` + `::test_signup_disabled_returns_403` (+ any documented vacuous skips). ZERO other failures — P3a is behaviour-preserving (enum authz unchanged; only `user_roles` rows added). List every failure; flag immediately if anything else fails.

- [ ] **Step 2: Behaviour-invariance proof (read-only reasoning, record it)**

`grep -rn "require_super_admin\|_require_owner_or_admin\|can_invite\|PlatformRole\.\|TenantRole\." apps/api/src/xtrusio_api/routes apps/api/src/xtrusio_api/core/auth.py apps/api/src/xtrusio_api/services/tenant_invites.py` — confirm P3a changed NO authorization check (the enum gates are byte-identical; only write paths + reconcile added). Confirm Alembic head still `0007` (`uv run --directory apps/api alembic heads`), no migration added.

- [ ] **Step 3: Grant-coverage proof (read-only against managed DB)**

```bash
uv run --directory apps/api python -c "import asyncio; from sqlalchemy import text; from xtrusio_api.core.db import SessionLocal
async def m():
 async with SessionLocal() as s:
  miss=(await s.execute(text(\"SELECT count(*) FROM tenant_memberships mm LEFT JOIN roles r ON r.scope='workspace' AND r.workspace_id=mm.tenant_id AND r.key=mm.role::text LEFT JOIN user_roles ur ON ur.auth_user_id=mm.user_id AND ur.role_id=r.id AND ur.workspace_id=mm.tenant_id WHERE ur.id IS NULL\"))).scalar_one()
  print('memberships_without_grant',miss)
asyncio.run(m())"
```
Expected `memberships_without_grant 0` after `make rbac-seed` (every enum membership now has a `user_roles` grant — the precondition P3b relies on).

- [ ] **Step 4: Lint/type + single head**

`uv run ruff check apps/api` + `uv run mypy --strict apps/api/src` (baseline only) ; `uv run --directory apps/api alembic heads` (one head `0007`).

- [ ] **Step 5: No commit.** Report results to the controller.

---

## Self-Review (completed during planning)

**Spec coverage (P3 §10 — the write-path/reconciliation subset):**
- "onboarding + invite-acceptance write `user_roles`" → Tasks 2, 3.
- bootstrap writes `user_roles` (super_admin) honoring the single-super_admin invariant → Task 4.
- "fully reconcile existing `tenant_memberships`/`platform_users` → `user_roles`" (the P2→P3 precondition before the disjunct is retired) → Task 5 (`reconcile_user_roles_from_enums` + startup/make wiring) + Task 1 (`grant_role`).
- Behaviour-preservation (enum authz unchanged; only additive) → enforced as a hard invariant + the gate's grep/full-suite proof.

**Explicitly OUT of P3a (deferred — NOT missing):** `core/permissions.py` / `require_permission` / route + service authz conversion / `/me` effective perms (P3b); audit-log writes, privilege-escalation guard + trigger, single-super_admin Python enforcement, migration `0008` retiring the `OR 0003-enum` disjunct, enum-column drop (P3c). P3a adds NO migration and changes NO authz decision.

**Placeholder scan:** none — every code step has concrete code from the verified surface map. Task 2 Step 1 / Task 3 Step 1 deliberately instruct "read & confirm exact current structure then apply the shown change" because the precise insert point depends on file structure the implementer must read (the *change* itself is fully specified); this is a read-first instruction, not a placeholder.

**Type/name consistency:** `grant_role(db, *, auth_user_id, scope, key, workspace_id=None, granted_by=None)` signature consistent across Tasks 1–4; `reconcile_user_roles_from_enums(db)` consistent Tasks 5–6; the fixed super_admin role id `00000000-0000-0000-0000-0000000000a1` consistent with `0006`/`0007`; enum→key mapping (`invite.role.value`, `TenantRole.OWNER`→`'owner'`, platform `'admin'` only, `'editor'` platform-unmapped) consistent with `0006`'s backfill + spec §2.7.

**Risk flagged for the spec-compliance reviewer:** the load-bearing claim is **behaviour-invariance** — P3a must not change a single authorization outcome. The reviewer must (a) diff every `routes/`/`core/auth.py`/`services/tenant_invites.py` authz check vs `main` and confirm zero change, (b) run the full pre-existing suite and confirm only the 2 documented env-failures, (c) confirm `make rbac-seed` drives `memberships_without_grant` to 0 (the precondition P3b depends on), and (d) confirm onboarding's new-workspace role seeding doesn't deadlock/duplicate against `reconcile_rbac` (Task 2 Step 1 ordering).
