## Summary

Phase 1 of the RBAC + RLS re-architecture: the **data-driven RBAC schema foundation**. Zero behaviour change — old enum columns are intentionally kept (nothing reads the new model until P3).

- **5 RBAC tables** (`permissions`, `roles`, `role_permissions`, `user_roles`, `rbac_audit_log`) + ORM models, in migration `0006_rbac_foundation` (single Alembic head, fully reversible, verified down→up on the populated managed DB).
- **Code-defined permission catalog** (`xtrusio_api.rbac.catalog`) + **idempotent reconciler** (`reconcile_rbac`) projecting it into `permissions` and wiring every `is_system` role's `role_permissions` (soft-deprecates removed keys, never deletes).
- **System-role seeds** (platform `super_admin`/`admin`; per-tenant workspace `owner`/`admin`/`editor`/`read_only`) + **backfill** of `user_roles` from the existing `platform_users.role` / `tenant_memberships.role` enums; invite tables get a nullable `role_id` (backfilled, enum kept).
- **Single-super_admin DB invariant**: partial unique index pinned to the fixed seeded role id `…00a1` (Postgres forbids subqueries in index predicates — mirrors the `id=1` singleton pattern in `0002`).
- **Startup reconcile hook** (best-effort `lifespan`, cannot crash boot) + `make rbac-seed`.
- **`test_no_super_admin_creation` guard** made RBAC-precise: matches super_admin *creation* only, not legitimate read-only role-key references.

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md`
Plan: `docs/superpowers/plans/2026-05-17-rbac-p1-schema-foundation.md`

7 tasks, each implemented via TDD with two-stage review (spec-compliance + code-quality) and a final whole-branch review → **READY TO MERGE** (no Critical/Important findings).

## Test status

- **All P1 tests green**; 2 intentional skips (managed DB currently has 0 tenants → per-workspace seed/backfill assertions are vacuous, explicitly skipped).
- **2 pre-existing failures, NOT introduced by this branch**: `tests/routes/test_signup.py::test_signup_status_default_false` and `::test_signup_disabled_returns_403`. Cause: the shared managed DB has `platform_settings.signups_enabled = true` (operator/smoke-test leftover state). These reproduce identically on pristine `origin/main`; P1 touches neither signup nor platform_settings code.
- Pre-existing `ruff I001` in 4 unrelated service files + 1 `jose` mypy baseline are byte-identical to `origin/main` (not this branch). P1 adds **zero** new ruff/mypy errors.

## Deploy / sequencing notes (must-read for whoever merges/deploys)

- **Deploy runbook:** `make migrate && make rbac-seed` (migration seeds role rows; the reconciler projects the permission catalog + role_permissions — the startup hook also self-heals running services).
- **P1→P2 sequencing constraint:** P1 enables RLS with deliberately permissive interim `*_authenticated_read USING(true)` policies (replaced by perm-aware policies in P2). Nothing reads the new tables until P3, so this is safe-by-isolation — but **P2 should follow P1 closely; do not leave P1 deployed long without P2.**
- Per-workspace seed/backfill paths are unexercised against real data (0 tenants in the managed DB); first real exercise is a later phase's tenant onboarding. Logic mirrors the verified platform path.

## Test Plan

- [ ] CI / reviewer: confirm `uv run --directory apps/api pytest tests/rbac/ tests/test_no_super_admin_creation.py` is fully green
- [ ] Confirm `make migrate` then `make migrate-down` round-trips cleanly (reversible)
- [ ] Confirm `make rbac-seed` prints `rbac reconcile complete` and `permissions` has the full catalog
- [ ] Acknowledge the 2 pre-existing `test_signup` failures are environmental (`signups_enabled=true`), not a P1 regression
