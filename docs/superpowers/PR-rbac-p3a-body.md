## Summary

RBAC re-architecture **Phase 3a — `user_roles` write-paths & reconciliation** (foundation slice of P3; P3b enforcement-conversion + `/me` effective perms, and P3c audit/governance/`0008` enum-disjunct retirement, are separate later phases). Builds on merged P2.

**Behaviour-preserving — ZERO authorization decision changed; legacy enum checks remain authoritative (P3b flips enforcement). No migration; single Alembic head `0007`.** This slice only *adds* `user_roles` grants + per-tenant workspace role rows/permissions so that every principal is resolver-visible before P3b switches the backend to the resolvers.

- **`rbac/grants.py::grant_role()`** — idempotent, reusable: resolve the `is_system` role by `(scope, key[, workspace_id])` (NULL-safe), `INSERT user_roles ... ON CONFLICT DO NOTHING`, raises `LookupError` on an unmapped key, no internal commit (caller owns the txn). Reused by all write paths + the reconciler; P3b/P3c will reuse it too.
- **`rbac/reconcile.py`** += `wire_workspace_role_perms(db,*,workspace_id)` (scoped, no-commit, one workspace's `role_permissions`) and `reconcile_user_roles_from_enums(db)` — Step A: idempotently seed missing per-tenant workspace system role **rows** for ALL tenants (0006-friendly tuples, `ON CONFLICT DO NOTHING`) + per-tenant scoped perm wiring; Step B: enum→`user_roles` backfill (platform projection guarded by `NOT EXISTS` — Postgres treats NULLs as *distinct* in `UNIQUE` so `ON CONFLICT(composite)` is inert for `workspace_id`-NULL platform rows, and the single-super_admin index is an expression partial index `ON ((true)) WHERE role_id='…00a1'` that `ON CONFLICT` cannot arbitrate; a genuine cross-identity breach still fails loud). One commit. `reconcile_rbac`/`_sync_role_perms` byte-unchanged.
- **onboarding** — ONE atomic commit: seed the new tenant's 4 system roles → scoped `wire_workspace_role_perms` → `grant_role(owner)`. No global reconcile on the request path; no partial-failure window.
- **invite-acceptance** — `_accept_platform` (admin only; `editor` has no platform system role; `super_admin` schema-unreachable) and `_accept_tenant` (all roles) write the matching grant in the SAME txn as the enum row, before the existing `IntegrityError→AlreadyProvisionedError` commit (re-accept idempotent).
- **bootstrap** — grants platform `super_admin`; `--force` clears the stale `user_roles …00a1` grant before recreating, upholding the single-super_admin global-singleton invariant across force/non-force/crash/re-run.
- **startup hook** (`main.py`) + `__main__.py`/`make rbac-seed` run both reconcilers (best-effort, boot-safe).

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` §5/§8/§10. Plan: `docs/superpowers/plans/2026-05-18-rbac-p3a-user-roles-write-paths.md`.

## Test status

Full backend suite from a **clean DB** (`make test-clean` first — required; shared-DB mid-run pollution otherwise causes false failures): **130 passed, 2 documented vacuous skips, 0 failed.** Behaviour-invariance proven: `git diff main...HEAD` for `routes/`, `core/auth.py`, `services/tenant_invites.py` is **EMPTY**; no migration; single head `0007`. Grant-coverage precondition for P3b satisfied: `memberships_without_grant 0`, `active_platform_without_grant 0`. ruff/mypy = documented baseline only (4 I001 + 1 jose, byte-identical to `main`). Final whole-slice code-quality review: no Critical/Important; clean/reusable/atomic; READY TO MERGE.

## P3b precondition (satisfied here)

Every enum principal now has a resolver-visible `user_roles` grant, so P3b can safely convert routes/services to `require_permission()` calling the `0007` resolvers without locking anyone out.

## Accepted deferred Minors (non-blocking)

bootstrap call-site self-heal comment; `reconcile.py` "byte-identical"→"semantically equivalent" docstring wording; optional teardown-via-CASCADE test simplification; `reconcile_user_roles_from_enums` O(tenants) startup-loop watch-item.

## Test Plan

- [ ] CI/reviewer: `uv run --directory apps/api python -m tests._cleanup` then `uv run --directory apps/api pytest tests/ -q` → only the 2 documented env-flaky `test_signup` (state-dependent) + 2 documented vacuous skips
- [ ] `git diff main...HEAD -- apps/api/src/xtrusio_api/routes apps/api/src/xtrusio_api/core/auth.py apps/api/src/xtrusio_api/services/tenant_invites.py` is EMPTY (behaviour-preserving)
- [ ] `uv run --directory apps/api alembic heads` = single `0007` (no migration)
- [ ] `make rbac-seed` runs twice idempotently (no IntegrityError)
