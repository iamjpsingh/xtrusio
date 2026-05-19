# HANDOFF — RBAC + RLS Re-architecture

**Written:** 2026-05-19
**Status:** **Backend RBAC re-architecture COMPLETE & merged** — P1, P2, P3a, P3b, P3c, P6a all in `main` (`5ddb413`). The enum→resolver authorization cutover is finished. Remaining: P4/P5 (RBAC admin APIs+UIs + the deferred P3c governance items), P6b/P6c (frontend permission-driven nav/shells + RBAC admin UIs), and the now-unblocked parked review-fix backlog.

Read top to bottom before doing anything.

---

## ⏩ RESUME HERE — 2026-05-19

### Done & merged (all PRs #1–#6 MERGED; `main` @ `5ddb413`; single Alembic head `0008`; 0 open PRs)

| Phase | What |
|---|---|
| P1 (#1) | RBAC schema: `permissions/roles/role_permissions/user_roles/rbac_audit_log`, code catalog, reconciler, system-role seeds, single-super_admin index, enum backfill |
| P2 (#3) | `0007` SECURITY DEFINER resolvers `has_platform_perm`/`has_workspace_perm`/`can_manage_role`; `0003` helpers → transition-safe `resolver OR 0003-enum` |
| P3a (#4) | `grant_role`; onboarding/invite-accept/bootstrap write `user_roles`; `reconcile_user_roles_from_enums` (+ startup/`make rbac-seed` wiring) — every principal resolver-visible |
| P3b (#5) | `core/permissions.py` (`require_permission` calling the resolvers); all 10 routes + tenant-invite service authz converted enum→resolver; `/me` additive effective-perm keys |
| P3c (#6) | `0008`: helpers → **pure resolver** (enum disjunct retired, reversible); pre-RBAC rls canaries reframed to grants. **Cutover complete.** |
| P6a (#2) | Frontend: pathless `_app` shell (shell-bleed fixed), shared `AuthLayout`, auth-page polish, public `/api/signup-status` rename |

Backend authorization is now **fully resolver/permission-driven** and consistent with RLS (same `0007` fns). Verified: full suite green from a CLEAN DB (0 failed; 2 documented vacuous skips; env-flaky `test_signup` state-dependent), `0007↔0008` reversible.

### NEXT (gated: each phase planned/executed only after the prior MERGED)

1. **P4 — Platform RBAC admin** (own branch off `main`, lean plan, lean execution): platform role/permission management API + UI for `super_admin` (`platform.roles.manage`) — create/edit/delete platform custom roles, attach catalog permissions, assign roles to platform users; platform audit-log viewer. Calls the `0007` resolvers / `require_permission` (P3b primitive) — reuse, don't re-invent. Spec §4/§9.
2. **P5 — Workspace RBAC admin**: per-workspace role/permission management API + UI for workspace `owner` (`workspace.roles.manage`), scope-isolated; workspace audit-log viewer; permission category grouping UI.
3. **Deferred-from-P3c, bundle with P4/P5** (they're only meaningful once human role/permission-mutation endpoints exist): **audit-log writes** on every RBAC mutation (the `rbac_audit_log` table exists since P1, still unwritten); **privilege-escalation guard** (service + DB trigger — actor can't grant perms they lack); **single-super_admin service-layer enforcement** (DB partial-unique index already enforces it; add the friendly service check). Use the existing `grant_role`/`require_permission`/resolvers.
4. **P6b** — pinned `/me` effective-perms TS contract + legacy-compat adapter + permission-driven nav + two physically-separate Platform/Workspace shells + workspace switcher. (P3b already returns the effective-perm keys additively; the enum `platform.role`/`tenants[].role` fields stay until P6b removes the frontend's enum consumption.)
5. **P6c** — RBAC admin UIs (consume P4/P5 APIs).
6. **🔒 LATE cleanup (only after P6b removes frontend enum consumption AND every backend enum read is gone):** drop `platform_users.role` / `tenant_memberships.role` columns + the `platform_role`/`tenant_role` enum types. Do NOT do this earlier — `/me` (P3b additive), onboarding/invite-accept/bootstrap still legitimately write the enum rows; `0008` downgrade restores the enum-reading OR-form so the enum columns must exist while `0008` is reversible.
7. **Parked review-fix backlog NOW UNBLOCKED:** memory `deferred-review-fixes-pending-p3` said "parked until RBAC P3 fully merges" — **P3 is now fully merged**, so those (CI, pagination, signup, JWKS, etc.) are eligible. Triage them into a phase when ready.

### Execution model (MANDATORY — memories `feedback_lean_review_workflow`, `feedback_model_selection`)

Build the whole phase/slice in a few coherent steps, clean/reusable/scalable code BY DESIGN. **ONE** full-suite run at the END of the slice via command, **run by the controller, not a subagent**, `make test-clean` first; the end-of-slice controller check MUST include `make check`-equivalent gates — **`ruff format --check` (not just `ruff check`) + `mypy --strict`** (a slice can be lint-clean but format-dirty — happened in P3c). Then **ONE** final code-quality review (Opus). Migrations/RLS/auth slices → ONE targeted mid-build check (controller, not full suite). Code/plan/migration subagents = **Opus**; Sonnet only for read-only exploration. Phases gated on prior-phase MERGE; never trust an implementer "no regression" without reproducing at the true baseline; serialized DB access + `_cleanup` before any suite run; code-quality bar unchanged (clean, reusable, scalable, mypy --strict, no demo data, RLS defense-in-depth). PRs: write a `docs/superpowers/PR-rbac-<phase>-body.md`, `gh pr create`, then `gh pr merge` (verify `gh pr view <n> --json state` = MERGED).

### Pre-existing `main` debt (unchanged, not from any phase)

- Managed DB `platform_settings.signups_enabled` live state → `tests/routes/test_signup.py::{test_signup_status_default_false,test_signup_disabled_returns_403}` env-flaky (pass/fail by state; reproduce on main).
- 4 ruff `I001` (`scripts/bootstrap.py`, `services/{signup,platform_invites,tenant_invites}.py`); 1 `jose` mypy; frontend `react-refresh` warnings — byte-identical to main, zero NEW from any phase.
- Shared-DB mid-run pollution fragility → ALWAYS `make test-clean` before a gate run; serialized DB access. (Bigger optional accelerator never adopted: a local Postgres test DB instead of remote managed Supabase.)

### Still USER-DRIVEN, never agent-run

Browser/e2e smokes needing real `.env` + `make dev`/OrbStack + real inboxes.

---

## Durable record

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` (§5 corrected for transition-safe→pure-resolver). Plans: `docs/superpowers/plans/2026-05-1{7,8,9}-rbac-*.md` (P1, P6a, P2, P3a, P3b, P3c). PR bodies: `docs/superpowers/PR-rbac-{p1,p6a,p2,p3a,p3b}-body.md` (+ P3c PR body inline in PR #6). Persistent memory at `~/.claude/projects/-Users-jpsingh-Developer-Project-xtrusio/memory/` is machine-local (does NOT travel) — this HANDOFF + spec + plans are the cross-machine record.
