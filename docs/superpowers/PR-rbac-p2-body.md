## Summary

RBAC re-architecture **Phase 2 — RLS permission engine**. DB-layer only (zero Python/app/model change; backend still uses enum reads until P3). Builds on merged P1 (`0006`).

Migration `0007_rls_permission_engine` (single Alembic head, fully reversible — `0006↔0007` round-trip re-proven clean on the managed DB):

- **Resolvers (single source of truth):** `has_platform_perm(uid,key)`, `has_workspace_perm(uid,tid,key)`, `can_manage_role(uid,rid)` — `SECURITY DEFINER STABLE`, resolve `user→user_roles→role_permissions→permissions` (exclude soft-deprecated perms), bypass RLS internally (no recursion — the `0003` technique). Both RLS **and the P3 backend** will call these exact functions.
- **Transition-safe supersession of the `0003` enum helpers:** `is_super_admin`/`is_tenant_owner_or_admin`/`is_tenant_member` rewritten to `new_resolver OR verbatim_0003_enum_check` — same signatures, so all ~13 existing `0003`/`0004` policies bind unchanged. This is a **true superset**: every principal authorized under `0003` stays authorized in the P2→P3 window (instant-revoke for RBAC-granted access via the resolver arm).
- **Perm-aware RBAC-table policies:** the 5 permissive `0006` interim policies (`*_authenticated_read`, `rbac_audit_log_no_read`) are dropped and replaced with `permissions_read` (catalog, public-to-authenticated), `roles_read`/`role_permissions_read` (scope-gated via resolvers/`can_manage_role`), `user_roles_read` (self OR scoped RBAC-manager — **closes the P1-flagged cross-tenant over-read**), `rbac_audit_log_read` (scope-appropriate `*.audit.read`).
- Reversible `downgrade()`: restore-`0006`-policies → restore-pure-enum-`0003`-helper-bodies → drop-resolvers.
- RLS test matrix in `tests/rls/test_permission_engine_rls.py` (resolver correctness both scopes, cross-scope isolation, genuinely-deprecated-present permission, delegation behaviour-preservation) + superseded the now-stale P1 `test_interim_rls_policies_present` with a forward `test_rbac_table_perm_aware_policies_present`.

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` §5 (corrected — see below). Plan: `docs/superpowers/plans/2026-05-17-rbac-p2-rls-permission-engine.md`.

Tasks 1, 2 (+ a mid-flight spec correction), 3, 3b, 4 — each via TDD with two-stage review + final whole-branch review → **READY TO MERGE** (no Critical/Important findings).

## ⚠️ Spec §5 correction landed in this PR (important)

Spec §5 originally prescribed *pure* delegation (`is_super_admin → has_platform_perm(...)` alone). The review/gate process **proved that wrong**: P1's backfill is a one-time snapshot; enum-era onboarding/invite code keeps creating `tenant_memberships`/`platform_users` rows with no `user_roles` grant until P3, so pure delegation **locks newly-onboarded owners out** (pre-RBAC `tests/rls/` passes at `0006`, fails under pure-`0007`). Corrected to the transition-safe `resolver OR 0003-enum` superset (contradiction with §7.5 "nothing breaks mid-flight" resolved). Spec §5 + HANDOFF document this.

## 🔒 P2→P3 sequencing constraint (must-read for whoever does P3)

The legacy disjunct is **load-bearing** for the P2→P3 window. **P3 must (a) make `user_roles` the write path (onboarding/invite-acceptance write `user_roles`), (b) fully reconcile existing `tenant_memberships`/`platform_users` into `user_roles`, (c) rewrite these 3 helper bodies to pure-resolver, and only THEN drop the enum columns.** Dropping enum columns before retiring the disjunct breaks every enum-only principal. Recorded in spec §5 + HANDOFF.

## Test status

- Full `tests/rls/` **24/24 at `0007`**; **9/9 pre-RBAC at `0006`**; both Task-2 regression canaries (`test_member_sees_only_their_tenants`, `test_editor_cannot_see_invites`) green; reversible round-trip clean; single head `0007`.
- Full backend suite green **except only** the 2 pre-existing env-flaky `tests/routes/test_signup.py::{test_signup_status_default_false,test_signup_disabled_returns_403}` (managed DB `signups_enabled` live state; reproduce on `main`, unrelated to P2) + 2 documented vacuous-data skips.
- Zero new ruff/mypy vs the documented `main` baseline (4 I001 unrelated, 1 jose).

## Operational note (live-DB)

`0007` was iterated across subagent tasks on a shared DB; each `make migrate` after the first was an alembic no-op. It was reconciled via the migration's own SQL (no alembic-state hand-edit) and the `0006↔0007` round-trip independently re-proven. If any environment is stuck at an intermediate `0007`: `make migrate-down` to `0006` before pulling, then `make migrate`. A fresh DB applies the complete final `0007` in one pass (ordering verified: resolvers → helpers → policies; downgrade exact inverse).

## Test Plan

- [ ] CI/reviewer: `uv run --directory apps/api pytest tests/rls/ -v` → 24/24 at `0007`
- [ ] `make migrate-down` → `tests/rls/ -k "not permission_engine"` 9/9 at `0006` → `make migrate` → 24/24 again (reversibility + transition-safe superset)
- [ ] `uv run --directory apps/api pytest tests/ -q` → only the 2 documented env `test_signup` failures + 2 documented skips
- [ ] Confirm single Alembic head `0007`; ruff/mypy = documented baseline only
- [ ] Acknowledge the P2→P3 retire-legacy-disjunct-before-dropping-enum-columns constraint
