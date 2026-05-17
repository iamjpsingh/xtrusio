# HANDOFF — RBAC + RLS Re-architecture

**Written:** 2026-05-17 (EOD)
**Status:** P1 **merged to main**. P6a **open as PR #2**. P2 (RLS engine) **code-complete on branch `rbac-p2-rls-engine`, Tasks 1–3 done + two-stage-reviewed; Task 4 gate + final whole-branch review + finishing NOT yet done.** P3–P5, P6b, P6c not started.

Read top to bottom before doing anything.

---

## ⏩ RESUME HERE — 2026-05-17 EOD

### PR / branch state

| Branch | Phase | State |
|---|---|---|
| `main` @ `6be1e2f` | — | P1 merged here (`gh pr 1` MERGED). P6a/P2 NOT in main. |
| `p6a-frontend-shell-auth-pages` | **P6a** frontend shell/auth | **PR #2 OPEN** — ready to merge (independent of P1/P2). Body: `docs/superpowers/PR-rbac-p6a-body.md`. |
| `rbac-p2-rls-engine` (tip `5ec2940`) | **P2** RLS engine | Tasks 1–3 done + reviewed. **NOT yet gated/PR'd.** |

`gh` is installed **and authenticated** (token has `repo`). PR #1 was merged via `gh pr merge 1 --merge` (the user's earlier "merged PR #1" hadn't actually gone through on GitHub — always verify `gh pr view <n> --json state` before acting on a "merged" claim).

### NEXT actions (in order) — tomorrow

1. **P2 Task 4 — whole-phase gate** (verification only, NO code; plan `docs/superpowers/plans/2026-05-17-rbac-p2-rls-permission-engine.md` Task 4). Was about to run when we stopped. Run: full reversibility round-trip (`alembic` 0007→0006→0007, single head 0007); `tests/rls/` = **9/9 pre-RBAC at 0006**, **full suite all-green at 0007** incl. the Task-2 canaries `test_member_sees_only_their_tenants` + `test_editor_cannot_see_invites` + all `test_permission_engine_rls.py`; full backend suite green except ONLY the 2 documented env-failures; ruff/mypy baseline only; one Alembic head `0007`.
2. **Final whole-branch P2 review** (opus, like P1/P6a) → then `superpowers:finishing-a-development-branch` → push + `gh pr create` for `rbac-p2-rls-engine` (independent PR; document the P2→P3 carry-forward + the live-DB reconcile gotcha below).
3. **Merge P6a (PR #2)** and the P2 PR whenever ready (both independent of each other; P2 depends on merged P1, which is done).
4. **P3** — write its plan only after P2 merges (P3 builds on merged P2). P3 scope (spec §10): backend `require_permission()` replaces enum checks; `/me` returns effective perms; onboarding/invite-acceptance **write `user_roles`**; audit writes; privilege-escalation guard + single-super_admin invariant enforcement. **P3 MUST also rewrite the 3 `0007` helper bodies from the transition-safe `resolver OR 0003-enum` form to PURE resolver, and only then may drop the enum columns** (spec §5, recorded). Then P4/P5 (RBAC admin APIs+UIs + audit viewers), P6b (pinned `/me` effective-perms TS contract + legacy adapter + permission-driven nav + two shells + workspace switcher), P6c (RBAC admin UIs).

Process unchanged: `writing-plans` → `subagent-driven-development` (subagent/task → spec-compliance review → code-quality review → fix loop → commit) → final whole-branch review → `finishing-a-development-branch`. The two-stage review + controller verification caught **a spec-level flaw in P2** (see below) and 8+ other plan/code bugs — keep it; do NOT trust an implementer's "no regression" claim without independently reproducing at the true baseline.

### ⚠️ P2 spec correction (important — already applied)

Spec §5 originally said pure delegation (`is_super_admin → has_platform_perm(...)` alone). That is **NOT behaviour-preserving** in the P2→P3 window: P1's backfill is a one-time snapshot; enum-era onboarding/invite code keeps writing `tenant_memberships`/`platform_users` with no `user_roles` grant until P3, so pure delegation **locks newly-onboarded owners out** (proven: pre-RBAC `tests/rls/` passes at DB `0006`, fails at pure-`0007`). **Corrected (committed in `db2247f`):** each `0003` helper body is now `new_resolver OR original_0003_enum_check` — a true superset, breaks nothing mid-flight (honors spec §7.5), instant-revoke for RBAC-granted access. Spec §5 + the P2 plan document this and the **P3-retires-the-legacy-disjunct** obligation. The pre-RBAC `tests/rls/` suite is the regression guard (must stay green at `0007`).

### ⚠️ Live-shared-DB gotcha (operational — from iterating one migration across 3 subagent tasks)

Migration `0007` was extended by Tasks 1→2→3. On the shared managed DB, each `make migrate` after the first was a **no-op** (alembic already had `0007` stamped), so the live DB sat at a "transitional 0007" missing later-added statements until an explicit `migrate-down`→`migrate`. The Task-3 implementer did a **one-time reconcile via the migration's own SQL** (no alembic-state hand-edit); the managed DB is now at the **correct final `0007`** and cycles cleanly both ways (re-verified by spec+code review). **If any other environment/DB is stuck at an intermediate `0007`: `make migrate-down` to `0006` BEFORE pulling this branch's latest, then `make migrate`.** Tomorrow's Task-4 gate re-proves the round-trip from the current (correct) state.

### Pre-existing `main` debt (NOT from P1/P6a/P2 — flagged, unchanged)

- Managed DB `platform_settings.signups_enabled=true` (operator/smoke leftover) → `tests/routes/test_signup.py::test_signup_status_default_false` + `::test_signup_disabled_returns_403` fail on `main` itself. Reset the setting or accept as known.
- 4 ruff `I001` (`scripts/bootstrap.py`, `services/{signup,platform_invites,tenant_invites}.py`); 1 `jose` mypy in `core/auth.py`; 5 frontend `react-refresh` warnings — all byte-identical to `main`. Zero NEW from any phase.

### P2 deferred Minors (non-blocking, optional follow-up)

Code review APPROVED Tasks 1–3. Optional: extract an `_ephemeral_auth_user()` test helper (≈30 dup lines in `test_permission_engine_rls.py`); a one-line comment on the `downgrade()` resolver-drop vs helper-revert asymmetry; module-top `reconcile_rbac` import. None block.

### Conventions in force

`docs/superpowers/ENGINEERING_PRINCIPLES.md`. NO `Co-Authored-By` trailer. Migrations pure raw SQL, reversible, single Alembic head. SECURITY DEFINER resolvers (`has_platform_perm`/`has_workspace_perm`/`can_manage_role`) are the single source of truth — P3 backend `require_permission()` calls the SAME fns. Test-data hygiene: never create/grant a `super_admin` (P1 single-super_admin partial unique index + `test_no_super_admin_creation` guard forbid it); ephemeral `@example.com` + FK-safe `finally` teardown; positive super_admin via the read-only `existing_super_admin` fixture. `make check` is the merge contract (red ONLY due to the pre-existing `signups_enabled` + ruff baseline above).

### Still USER-DRIVEN, never agent-run

Browser/e2e smokes needing real `.env` + `make dev`/OrbStack + real inboxes.

---

## Durable record

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` (§5 corrected). Plans: `docs/superpowers/plans/2026-05-17-rbac-p1-schema-foundation.md`, `…-p6a-frontend-shell-and-auth-pages.md`, `…-p2-rls-permission-engine.md`. PR bodies: `docs/superpowers/PR-rbac-p1-body.md`, `…-p6a-body.md`. Persistent memory at `~/.claude/projects/-Users-jpsingh-Developer-Project-xtrusio/memory/` is machine-local (does NOT travel) — this HANDOFF + spec + plans are the cross-machine record.
