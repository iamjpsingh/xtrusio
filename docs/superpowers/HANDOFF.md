# HANDOFF — RBAC + RLS Re-architecture

**Written:** 2026-05-17
**Status:** Spec approved. **P1 (schema foundation)** and **P6a (frontend shell/auth-pages)** code-complete, fully reviewed, pushed as **two independent open PRs** (not yet merged). P2–P5, P6b, P6c not started.

Read this top to bottom before doing anything.

---

## ⏩ RESUME HERE — 2026-05-17

### What exists now

- **Spec (approved):** `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` — the authoritative design. Locked decisions: platform vs workspace = two fully separate authz domains (one shared `auth.users` login); **code-defined permission catalog** + roles-as-data + `role_permissions` + `user_roles` (multi-role, effective = union); DB-enforced RLS via `SECURITY DEFINER` `has_platform_perm`/`has_workspace_perm` that **both RLS and backend call**; super_admin owns platform RBAC (singleton, bootstrap-only), platform admins operate; workspace `owner` governs RBAC within their workspace; seed roles immutable; privilege-escalation guard; audit log (recorded + UI); permission categories. 6-phase decomposition P1–P6 (P6 split into P6a/P6b/P6c).

- **Two open PRs, both cut from `main` (`21477b3`), independent of each other:**

  | Branch | Phase | PR body | State |
  |---|---|---|---|
  | `rbac-rls-rearchitecture` | **P1** schema foundation | `docs/superpowers/PR-rbac-p1-body.md` | pushed, READY TO MERGE |
  | `p6a-frontend-shell-auth-pages` | **P6a** frontend shell/auth | `docs/superpowers/PR-rbac-p6a-body.md` | pushed, READY TO MERGE |

  PR creation URLs (gh now installed but not authed — `gh auth login` or use the URLs):
  `https://github.com/iamjpsingh/xtrusio/compare/main...rbac-rls-rearchitecture?expand=1`
  `https://github.com/iamjpsingh/xtrusio/compare/main...p6a-frontend-shell-auth-pages?expand=1`

- **P1 delivers:** migration `0006_rbac_foundation` (5 RBAC tables `permissions`/`roles`/`role_permissions`/`user_roles`/`rbac_audit_log` + grants + RLS-enable + interim permissive `*_authenticated_read` policies + single-super_admin partial unique index pinned to fixed role id `00000000-0000-0000-0000-0000000000a1` + system-role seeds + enum→`user_roles` backfill + invite `role_id`, reversible); code permission catalog `xtrusio_api.rbac.catalog`; idempotent reconciler `xtrusio_api.rbac.reconcile.reconcile_rbac`; startup hook + `make rbac-seed`; RBAC-precise `test_no_super_admin_creation` guard. Old enum columns intentionally KEPT (nothing reads the new model until P3). Plans: `docs/superpowers/plans/2026-05-17-rbac-p1-schema-foundation.md`.

- **P6a delivers:** pathless `routes/_app.tsx` shell layout → **shell-bleed structurally fixed** (auth pages root-level, in-app under `_app`, URLs unchanged, real-router boundary test guards it); shared `AuthLayout` (dark card) consumed by sign-in/sign-up/onboarding/accept-invite; `ApiError.message` debt fixed (sign-up/onboarding now `errorMessage(errorCode(...))`); public `GET /api/signup-status` (old `/api/platform/signup-status` 404s, `/api/platform/settings` untouched) + "Public client signup" relabels; hermetic vitest env. `MeResponse`/`resolveRoute`/`AppSidebar`/`platformNav` deliberately UNCHANGED. Plan: `docs/superpowers/plans/2026-05-17-rbac-p6a-frontend-shell-and-auth-pages.md`.

### NEXT action (in order)

1. **Merge P1 and P6a** (either order — independent). P1's interim RLS is permissive; see sequencing constraint below.
2. **P2 — RLS engine** (write the plan once P1 is merged, since P2 builds on merged P1 code). Scope per spec §10: `has_platform_perm(uid,key)` / `has_workspace_perm(uid,tid,key)` `SECURITY DEFINER` fns; rewrite the migration-`0003` helpers `is_super_admin`/`is_tenant_owner_or_admin`/`is_tenant_member` to delegate to them; replace P1's interim `*_authenticated_read USING(true)` policies with perm-aware policies; full RLS test matrix. **P2 must follow P1 closely** (see constraint).
3. Then **P3** (backend `require_permission()` replaces enum checks; `/me` returns effective perms; invites create `user_roles`; audit writes; privilege-escalation guard + single-super_admin invariant enforcement) → **P4/P5** (platform & workspace RBAC admin APIs+UIs + audit viewers) → **P6b** (pinned `/me` effective-perms TS contract + legacy-compat adapter + TS permission-catalog mirror + permission-driven nav + two Platform/Workspace shells + workspace switcher) → **P6c** (RBAC admin UIs against the pinned contract).

Process: each phase = own plan (`writing-plans`) executed via `superpowers:subagent-driven-development` (one subagent/task → spec-compliance review → code-quality review → fix loop → commit), final whole-branch review, then `finishing-a-development-branch`. The two-stage review has caught 8+ real plan/code bugs — keep it.

### ⚠️ Constraints / carry-forward

- **P1→P2 sequencing:** P1 enables RLS with deliberately permissive interim `*_authenticated_read USING(true)` policies (so `user_roles` is readable by any authenticated user). Safe-by-isolation now (nothing reads the new tables until P3) but **do not leave P1 deployed long without P2**; P2 replaces these with perm-aware policies.
- **Deploy runbook:** `make migrate && make rbac-seed` (migration seeds role rows; reconciler projects the permission catalog + role_permissions; the startup hook self-heals running services).
- **P6b contract-pinning:** the `/me` effective-permissions TS type + RBAC-admin client must be derived from spec §5/§8 + the P1 `catalog.py` keys, with a legacy-compat adapter so the frontend works while the backend still returns the old enum `/me` (pre-P3). When P2–P5 land they must conform to this pinned contract.
- **P6b copy refinement (deferred):** accept-invite error state still shows subtitle "One moment while we set up your access"; the specific "Couldn't accept invitation" `<h1>` was dropped under the shared single-title constraint. Refine per-state auth copy in P6b.
- Per-workspace seed/backfill paths unexercised against real data (0 tenants in managed DB); first real exercise is later-phase tenant onboarding.

### Pre-existing `main` debt (NOT from P1/P6a — flagged for the operator)

- Managed DB has `platform_settings.signups_enabled = true` (leftover operator/smoke state) → `tests/routes/test_signup.py::test_signup_status_default_false` + `::test_signup_disabled_returns_403` fail on `main` itself. Reset the setting to fix, or accept as known. NOT a P1/P6a regression.
- 4 ruff `I001` in `scripts/bootstrap.py` + `services/{signup,platform_invites,tenant_invites}.py`; 1 `jose` mypy baseline in `core/auth.py`; 5 frontend `react-refresh/only-export-components` warnings — all byte-identical to `main`. Zero NEW from P1/P6a.

### Test baselines

- P1 branch: backend rbac suite green (2 intentional skips — 0 tenants); migration reversible (down→up verified on managed DB); zero new ruff/mypy.
- P6a branch: frontend **38/38**, `turbo typecheck` clean, eslint 0 errors; backend only the 2 documented env failures.
- Managed DB: 1 real `platform_users` super_admin (`admin@xtrusio.com`); after `make migrate && make rbac-seed`, `permissions` holds the 16-key catalog, system roles seeded, the real super_admin backfilled to one `user_roles` grant.

### Conventions in force

`docs/superpowers/ENGINEERING_PRINCIPLES.md`. NO `Co-Authored-By` trailer (memories `feedback_no_claude_coauthor`, `feedback_test_data_hygiene`, `feedback_no_hardcoded_config`, `project_apierror_message_debt`). Migrations pure raw SQL, reversible, single Alembic head. Tests never create a super_admin / no `@example.com` writes. `make check` is the merge contract (currently red ONLY due to the pre-existing `signups_enabled` + ruff baseline above).

### Still USER-DRIVEN, never agent-run

Browser smokes needing real `.env` + `make dev`/OrbStack + real inboxes: P6a `/sign-up` incognito (dark card, no sidebar); any signup/invite e2e. `gh` is installed but unauthenticated — opening PRs needs `gh auth login` (interactive) or the compare URLs above.

---

## Memory

Persistent memory at `~/.claude/projects/-Users-jpsingh-Developer-Project-xtrusio/memory/` (machine-local, does NOT travel). This HANDOFF.md + the spec + the P1/P6a plan files + the two PR-body docs are the durable cross-machine record.
