# HANDOFF — RBAC + RLS Re-architecture

**Written:** 2026-05-17
**Status:** P1 **merged to main**. P6a **PR #2 OPEN**. P2 (RLS engine) **complete + fully reviewed (final review READY TO MERGE), PR #3 OPEN**. P3–P5, P6b, P6c not started.

Read top to bottom before doing anything.

---

## ⏩ RESUME HERE — 2026-05-17

### PR / branch state

| Branch | Phase | State |
|---|---|---|
| `main` @ `6be1e2f` | — | P1 merged (`gh pr 1` MERGED). P6a/P2 NOT in main yet. |
| `p6a-frontend-shell-auth-pages` | **P6a** frontend shell/auth | **PR #2 OPEN** — READY TO MERGE (independent). Body: `docs/superpowers/PR-rbac-p6a-body.md`. |
| `rbac-p2-rls-engine` (tip `9c89f6c`) | **P2** RLS engine | **PR #3 OPEN** — all tasks (1,2,3,3b,4) + final whole-branch review done, READY TO MERGE. Body: `docs/superpowers/PR-rbac-p2-body.md`. |

`gh` installed **and authenticated** (token `repo`). Always `gh pr view <n> --json state` before acting on a "merged" claim (PR #1's first "merged" hadn't gone through; merged via `gh pr merge 1 --merge`).

### NEXT actions (in order)

1. **Merge PR #2 (P6a) and PR #3 (P2).** Both independent of each other; both build only on merged P1 (done). Either order. Verify each merge actually lands (`gh pr view <n> --json state` = MERGED; `git ls-remote origin main` moved).
2. **P3 — gated on P2 merge.** Do NOT start P3 until PR #3 is merged into `main` (this merge-gate discipline is exactly what caught the P2 spec flaw; stacking P3 on unmerged P2 is the anti-pattern). After P2 merges: `git checkout main && git merge --ff-only origin/main`, verify `0007` + the resolvers are on main, cut `rbac-p3-…`, write the P3 plan (`writing-plans`) against the merged code, execute via `subagent-driven-development`.
3. **P3 scope (spec §10):** backend `require_permission()`/`require_workspace_permission()` deps replace ALL enum checks; `/me` returns effective perm keys (platform set + per-workspace map) — calls the SAME `has_*_perm` resolvers; onboarding + invite-acceptance **write `user_roles`**; audit-log writes on RBAC mutations; privilege-escalation guard (service + DB trigger) + single-super_admin invariant enforcement. **CRITICAL P2→P3 obligation:** P3 must rewrite the 3 `0007` helper bodies from transition-safe `resolver OR 0003-enum` to **pure resolver**, fully reconcile existing `tenant_memberships`/`platform_users` → `user_roles`, and only THEN may a later step drop the enum columns. Dropping enum columns while the legacy disjunct or enum-only principals exist breaks access. (Recorded in spec §5 + PR #3 body.)
4. Then P4/P5 (platform & workspace RBAC admin APIs+UIs + audit viewers), P6b (pinned `/me` effective-perms TS contract + legacy adapter + permission-driven nav + two Platform/Workspace shells + workspace switcher), P6c (RBAC admin UIs).
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
