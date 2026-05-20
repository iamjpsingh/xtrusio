# HANDOFF — RBAC + RLS Re-architecture

**Written:** 2026-05-19, updated 2026-05-20 (P3.5 merged)
**Status:** **Backend RBAC re-architecture COMPLETE & merged** — P1, P2, P3a, P3b, P3c, P6a, P3.5 all in `main` (`e315dc5`). The enum→resolver authorization cutover is finished and the parked review-fix backlog is now drained except for surfaced follow-ups (see below). Remaining: P4/P5 (RBAC admin APIs+UIs + the deferred P3c governance items), P6b/P6c (frontend permission-driven nav/shells + RBAC admin UIs).

Read top to bottom before doing anything.

---

## ⏩ RESUME HERE — 2026-05-20

### Done & merged (PRs #1–#6, #8 MERGED; `main` @ `e315dc5`; single Alembic head `0008`; 0 open PRs)

| Phase | What |
|---|---|
| P1 (#1) | RBAC schema: `permissions/roles/role_permissions/user_roles/rbac_audit_log`, code catalog, reconciler, system-role seeds, single-super_admin index, enum backfill |
| P2 (#3) | `0007` SECURITY DEFINER resolvers `has_platform_perm`/`has_workspace_perm`/`can_manage_role`; `0003` helpers → transition-safe `resolver OR 0003-enum` |
| P3a (#4) | `grant_role`; onboarding/invite-accept/bootstrap write `user_roles`; `reconcile_user_roles_from_enums` (+ startup/`make rbac-seed` wiring) — every principal resolver-visible |
| P3b (#5) | `core/permissions.py` (`require_permission` calling the resolvers); all 10 routes + tenant-invite service authz converted enum→resolver; `/me` additive effective-perm keys |
| P3c (#6) | `0008`: helpers → **pure resolver** (enum disjunct retired, reversible); pre-RBAC rls canaries reframed to grants. **Cutover complete.** |
| P6a (#2) | Frontend: pathless `_app` shell (shell-bleed fixed), shared `AuthLayout`, auth-page polish, public `/api/signup-status` rename |
| P3.5 (#8) | Review-fix backlog: CI workflow (`.github/workflows/ci.yml`), cursor pagination on 3 list endpoints + structural invariant test, JWKS coalescing lock, signup duplicate-email by `AuthApiError` class, lifespan fail-fast (`STARTUP_RECONCILE_TOLERANT` escape hatch), AuthGuard duplicate-staleTime cleanup. Principles §8 amended to permit managed-Supabase test project. Plan + PR body in `docs/superpowers/`. |

Backend authorization is now **fully resolver/permission-driven** and consistent with RLS (same `0007` fns). Verified: full suite green from a CLEAN DB (0 failed; 2 documented vacuous skips; env-flaky `test_signup` state-dependent), `0007↔0008` reversible.

### NEXT (gated: each phase planned/executed only after the prior MERGED)

1. **P4 — Platform RBAC admin** (own branch off `main`, lean plan, lean execution): platform role/permission management API + UI for `super_admin` (`platform.roles.manage`) — create/edit/delete platform custom roles, attach catalog permissions, assign roles to platform users; platform audit-log viewer. Calls the `0007` resolvers / `require_permission` (P3b primitive) — reuse, don't re-invent. Spec §4/§9.
2. **P5 — Workspace RBAC admin**: per-workspace role/permission management API + UI for workspace `owner` (`workspace.roles.manage`), scope-isolated; workspace audit-log viewer; permission category grouping UI.
3. **Deferred-from-P3c, bundle with P4/P5** (they're only meaningful once human role/permission-mutation endpoints exist): **audit-log writes** on every RBAC mutation (the `rbac_audit_log` table exists since P1, still unwritten); **privilege-escalation guard** (service + DB trigger — actor can't grant perms they lack); **single-super_admin service-layer enforcement** (DB partial-unique index already enforces it; add the friendly service check). Use the existing `grant_role`/`require_permission`/resolvers.
4. **P6b** — pinned `/me` effective-perms TS contract + legacy-compat adapter + permission-driven nav + two physically-separate Platform/Workspace shells + workspace switcher. (P3b already returns the effective-perm keys additively; the enum `platform.role`/`tenants[].role` fields stay until P6b removes the frontend's enum consumption.)
5. **P6c** — RBAC admin UIs (consume P4/P5 APIs).
6. **🔒 LATE cleanup (only after P6b removes frontend enum consumption AND every backend enum read is gone):** drop `platform_users.role` / `tenant_memberships.role` columns + the `platform_role`/`tenant_role` enum types. Do NOT do this earlier — `/me` (P3b additive), onboarding/invite-accept/bootstrap still legitimately write the enum rows; `0008` downgrade restores the enum-reading OR-form so the enum columns must exist while `0008` is reversible.
7. ~~**Parked review-fix backlog NOW UNBLOCKED**~~ — **DRAINED by P3.5 (#8, merged 2026-05-20)**. Remaining surfaced follow-ups (not in P3.5 scope, captured for a future phase):
   - **Pre-existing test-file typecheck debt:** `uv run mypy apps/api` reports ~49 `no-untyped-def` errors in P3a/P3b-era test files (test_onboarding, test_me, test_signup, test_platform_settings, test_invite_acceptance, test_tenants, test_platform_invites, test_tenant_invites, test_signup_to_tenant_flow, test_invite_full_flow, test_permission_engine_rls). P3.5 contributed zero new mypy errors; every new source/test in #8 is fully typed. Propose a small "type the tests" phase before P4, OR absorb into P4 prep.
   - **`gotrue` → `supabase_auth` migration:** supabase-py 2.x emits a `DeprecationWarning` saying `gotrue` is being replaced by `supabase_auth`. Migrate imports in a future phase.
   - **Pre-existing broad `except Exception` in invite services:** `services/platform_invites.py:90` and `services/tenant_invites.py:146` swallow every exception class into `EmailProviderUnavailableError`. Narrow to specific (`httpx.HTTPError`, `AuthApiError`, `AuthRetryableError`, etc.) in a follow-up audit.

### P3.5 (#8) operator artifacts

After P3.5 you MUST have these in place for local dev:

- `.env` includes `STARTUP_RECONCILE_TOLERANT=false` (required Settings field, no `Field` default per `feedback_no_hardcoded_config`). Without it, every `make dev`/`make test`/`make api` fails Settings validation at boot.
- GitHub Actions secrets configured for the `xtrusio-ci` managed Supabase project: `CI_DATABASE_URL`, `CI_SUPABASE_URL`, `CI_SUPABASE_ANON_KEY`, `CI_SUPABASE_SERVICE_ROLE_KEY`, `CI_SUPABASE_JWKS_URL`. Until set, the workflow on every PR will go red at the `Migrate test DB` step — expected and benign for merging (CI gates are advisory not blocking until secrets land).

### Execution model (MANDATORY — memories `feedback_lean_review_workflow`, `feedback_model_selection`)

Build the whole phase/slice in a few coherent steps, clean/reusable/scalable code BY DESIGN. **ONE** full-suite run at the END of the slice via command, **run by the controller, not a subagent**, `make test-clean` first; the end-of-slice controller check MUST include `make check`-equivalent gates — **`ruff format --check` (not just `ruff check`) + `mypy --strict`** (a slice can be lint-clean but format-dirty — happened in P3c). Then **ONE** final code-quality review (Opus). Migrations/RLS/auth slices → ONE targeted mid-build check (controller, not full suite). Code/plan/migration subagents = **Opus**; Sonnet only for read-only exploration. Phases gated on prior-phase MERGE; never trust an implementer "no regression" without reproducing at the true baseline; serialized DB access + `_cleanup` before any suite run; code-quality bar unchanged (clean, reusable, scalable, mypy --strict, no demo data, RLS defense-in-depth). PRs: write a `docs/superpowers/PR-rbac-<phase>-body.md`, `gh pr create`, then `gh pr merge` (verify `gh pr view <n> --json state` = MERGED).

### Pre-existing `main` debt (unchanged, not from any phase)

- Managed DB `platform_settings.signups_enabled` live state → `tests/routes/test_signup.py::{test_signup_status_default_false,test_signup_disabled_returns_403}` env-flaky (pass/fail by state; reproduce on main).
- Test-file typecheck debt: ~49 `no-untyped-def` mypy errors in P3a/P3b-era test files — see "P3.5 surfaced follow-ups" above. Previously under-counted as "1 jose mypy"; the real number was already in the test tree pre-P3.5.
- Shared-DB mid-run pollution fragility → ALWAYS `make test-clean` before a gate run; serialized DB access. (Bigger optional accelerator never adopted: a local Postgres test DB instead of remote managed Supabase.)

### Still USER-DRIVEN, never agent-run

Browser/e2e smokes needing real `.env` + `make dev`/OrbStack + real inboxes.

---

## Durable record

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` (§5 corrected for transition-safe→pure-resolver). Plans: `docs/superpowers/plans/2026-05-1{7,8,9}-rbac-*.md` (P1, P6a, P2, P3a, P3b, P3c). PR bodies: `docs/superpowers/PR-rbac-{p1,p6a,p2,p3a,p3b}-body.md` (+ P3c PR body inline in PR #6). Persistent memory at `~/.claude/projects/-Users-jpsingh-Developer-Project-xtrusio/memory/` is machine-local (does NOT travel) — this HANDOFF + spec + plans are the cross-machine record.
