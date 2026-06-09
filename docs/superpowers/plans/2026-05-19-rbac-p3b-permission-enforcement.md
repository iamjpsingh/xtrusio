# RBAC P3b — Backend Permission Enforcement (lean plan)

> Execution: lean model (memory `feedback_lean_review_workflow`) — build the whole slice in coherent steps with clean/reusable code; ONE full-suite run at the end by the controller (not per-file/per-subagent); ONE final review; auth-gate exception → ONE targeted mid-build check (the auth route tests) before the full run. Code subagents = Opus (`feedback_model_selection`).

**Goal:** Replace every enum-based backend authorization check with the `0007` SECURITY DEFINER resolvers (`has_platform_perm`/`has_workspace_perm`) via a single reusable `core/permissions.py` primitive, and extend `/me` to return effective permission keys — so authorization is permission-driven per spec section 5/section 8/section 10.

**This intentionally CHANGES authorization** (not behaviour-preserving — that was P3a). Per the spec role→permission matrix, platform `admin` gains the operational perms it should have (clients/users/settings management), while `super_admin`-only `platform.roles.manage` stays super_admin-only. Tests asserting old enum-role 403s are **reframed** to the permission model — expected, in-scope. Precondition (every enum principal has a resolver-visible `user_roles` grant) is satisfied by merged P3a.

**Builds on merged P3a** (`main` @ `aef693e`): `0007` resolvers; `grant_role`; `reconcile_user_roles_from_enums`; every principal resolver-visible. No migration in P3b (single head `0007`).

---

## Route / service authz conversion map (authoritative)

Backend connects as owner (RLS does not constrain it) → authz MUST be explicit in Python. Identity deps are UNCHANGED (they keep the existing `auth.users`/`platform_users` active/provisioned guards); only the **role-enum check** becomes a **resolver permission check**.

| Endpoint | Current | → P3b permission (scope inferred from key prefix) |
|---|---|---|
| `POST /api/platform/users/invites` | `Depends(require_super_admin)` | `platform.users.invite` |
| `GET /api/platform/users/invites` | `Depends(require_super_admin)` | `platform.users.invite` |
| `DELETE /api/platform/users/invites/{id}` | `Depends(require_super_admin)` | `platform.users.manage` |
| `GET /api/platform/settings` | `Depends(get_current_user)` (no role check) | `platform.settings.read` |
| `PUT /api/platform/settings` | `Depends(require_super_admin)` | `platform.settings.manage` |
| `GET /api/tenants` | `Depends(require_super_admin)` | `platform.clients.read` |
| `POST /api/tenants` | `Depends(require_super_admin)` | `platform.clients.manage` |
| `POST /api/tenants/{tid}/invites` | service `_require_owner_or_admin` + `can_invite` | `workspace.members.invite` (workspace_id = path `tid`) — `can_invite` business rule STAYS |
| `GET /api/tenants/{tid}/invites` | service `_require_owner_or_admin` | `workspace.members.manage` (workspace_id = `tid`) |
| `DELETE /api/tenants/{tid}/invites/{id}` | service `_require_owner_or_admin` | `workspace.members.manage` (workspace_id = `tid`) |

`services/tenant_invites.py::_require_owner_or_admin` (the enum gate) is replaced by a resolver permission check at the route or service boundary; `can_invite()` (inviter-role-vs-target business rule) is unchanged.

---

## Tasks (coherent steps; build all, then one test run by controller)

### Task 1 — `core/permissions.py` (the reusable authz primitive)

Create `apps/api/src/xtrusio_api/core/permissions.py`:

```python
"""Resolver-backed permission checks — the single authz primitive.

Scope is inferred from the key prefix (`platform.` / `workspace.`). Calls the
0007 SECURITY DEFINER resolvers (the single source of truth shared with RLS).
The backend uses the owner DB connection (RLS does not constrain it), so authz
MUST be enforced here explicitly.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def has_permission(
    db: AsyncSession, user_id: UUID, key: str, workspace_id: UUID | None = None
) -> bool:
    scope = key.split(".", 1)[0]
    if scope == "platform":
        return bool(
            (
                await db.execute(
                    text("SELECT has_platform_perm(:u, :k)"),
                    {"u": user_id, "k": key},
                )
            ).scalar_one()
        )
    if scope == "workspace":
        if workspace_id is None:
            return False
        return bool(
            (
                await db.execute(
                    text("SELECT has_workspace_perm(:u, :t, :k)"),
                    {"u": user_id, "t": workspace_id, "k": key},
                )
            ).scalar_one()
        )
    return False


async def require_permission(
    db: AsyncSession, user_id: UUID, key: str, workspace_id: UUID | None = None
) -> None:
    """Raise 403 (detail='permission_denied') unless the user holds `key`."""
    if not await has_permission(db, user_id, key, workspace_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission_denied")
```

Reusable everywhere (routes call it after their existing identity dep; services call it directly). No FastAPI-dependency-factory needed — routes already inject identity + db; a direct `await require_permission(db, identity.user_id, "<key>"[, tid])` call after the identity dep is the clean minimal conversion and keeps each route's existing active/provisioned identity guard intact.

### Task 2 — convert the 7 platform routes + 3 tenant-invite routes/service

Per the map. For platform routes currently using `Depends(require_super_admin)`: keep an identity dep that still enforces provisioned+active (use `get_current_user` → `CurrentUser`, unchanged), then `await require_permission(db, user.user_id, "<key>")` as the first line of the handler (or a tiny shared route-dep). Replace the `require_super_admin` dep with `get_current_user` where the only thing it added was the role check (the permission call now does authz). `GET /api/platform/settings` (currently no check) gains `require_permission(..., "platform.settings.read")`. For `tenant_invites` routes/service: replace `_require_owner_or_admin(...)` with `await require_permission(db, inviter_id, "workspace.members.invite"|"workspace.members.manage", workspace_id=tenant_id)`; keep `can_invite()`; keep `NotAMemberError`→ a membership existence check is no longer the gate (the resolver is) — but preserve the existing 404/403 error-code contract the route tests assert (map a failed `require_permission` to the same HTTP/detail the old path returned where tests depend on it; otherwise 403 `permission_denied`). Delete now-dead `_require_owner_or_admin` if unused. Keep `require_super_admin` in `core/auth.py` only if still referenced; otherwise remove it (dead code).

### Task 3 — `/me` returns effective permissions (additive)

Extend `schemas/me.py` + `routes/me.py`: ADD to `MeResponse` a `platform_permissions: list[str]` and per-tenant effective `permissions: list[str]` on `TenantContext` (keep existing `platform.role`/`tenants[].role` fields — frontend P6b removes them later; additive = no frontend break). Compute by querying the catalog/resolver: for the platform set, `SELECT p.key FROM user_roles ur JOIN roles r ... JOIN role_permissions rp JOIN permissions p WHERE ur.auth_user_id=:u AND r.scope='platform' AND NOT p.is_deprecated`; per workspace likewise scoped to that `workspace_id`. (Single query each, deduped/sorted; reuse a small helper in `core/permissions.py`, e.g. `effective_platform_perms(db,uid)->list[str]` / `effective_workspace_perms(db,uid,tid)->list[str]`.)

### Task 4 — reframe affected tests to the permission model

Update route/auth tests that asserted enum-role outcomes (e.g. `test_create_invite_non_super_admin_returns_403`, `test_put_settings_requires_super_admin`, the tenant-invite owner/admin tests, `/me` shape tests). New expectations: a principal WITH the permission (granted via `grant_role`/P3a-style ephemeral setup) succeeds; WITHOUT → 403 `permission_denied`. `/me` tests assert the new `platform_permissions`/per-tenant `permissions` keys are present + correct for the seeded role. Reuse the established ephemeral `@example.com` + `grant_role`/role-seed + FK-safe `finally` patterns from P3a tests; NEVER create/grant a super_admin (use `existing_super_admin` for the positive super_admin path; for admin/owner/editor use ephemeral users granted the matching system role). Hygiene + the `test_no_super_admin_creation` guard still apply.

---

## Verification (lean — controller-run, ONCE)

1. **Auth-gate mid-build targeted check** (the lean-model exception, controller, NOT full suite): after Tasks 1–2, `uv run --directory apps/api python -m tests._cleanup` then `uv run --directory apps/api pytest tests/routes/ tests/rls/ -q` — confirm the converted routes enforce the permission model (no 500s; 403 `permission_denied` for unprivileged; success for privileged) and RLS still green. Fix before continuing.
2. **One full run at the end** (controller): `make test-clean` then `uv run --directory apps/api pytest tests/ -q`. Green except the 2 documented env-flaky `test_signup` (state-dependent) + 2 documented vacuous skips. ZERO others. `uv run ruff check apps/api` + `uv run mypy --strict apps/api/src` (baseline only). `alembic heads` single `0007`.
3. **One final code-quality review** (Opus, whole slice): correctness of the resolver-call conversion (every old enum gate now a correct permission key per the map; identity/active/provisioned guards preserved; tenant-invite error-code contract preserved; `can_invite` intact; no dead code; `/me` additive & correct; clean/reusable `core/permissions.py`). Then finishing → PR → merge.

## Out of scope (P3c / later — do NOT do here)

audit-log writes; privilege-escalation guard + DB trigger; single-super_admin Python enforcement; migration `0008` retiring the `OR 0003-enum` disjunct; dropping enum columns; frontend `/me` consumption / permission-driven nav / two shells (P6b). The legacy enum columns + transition-safe `0007` helpers stay; P3b only changes the *backend authz source* to the resolvers.

## Self-review

Covers spec section 10-P3 backend items: `require_permission` replaces all enum checks (Tasks 1–2, full route/service map); `/me` returns effective perms (Task 3); resolver = single source of truth shared with RLS (core/permissions.py calls the same `0007` fns). Risk: P3b changes live authz — mitigated by the explicit conversion map (each key spec-derived), preserving identity/active guards + the tenant-invite error-code contract, the auth-gate mid-build check, and reframed tests. Precondition (resolver-visible principals) satisfied by merged P3a.
