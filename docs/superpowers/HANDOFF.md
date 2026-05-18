# HANDOFF — RBAC + RLS Re-architecture

**Written:** 2026-05-18
**Status:** **P1, P6a, P2 all merged to `main`.** P3 next (gated on P2 merge — now satisfied). P4/P5, P6b, P6c not started.

Read top to bottom before doing anything.

---

## ⏩ RESUME HERE — 2026-05-18

### PR / branch state

| PR | Phase | State |
|---|---|---|
| #1 | **P1** schema foundation | MERGED |
| #2 | **P6a** frontend shell/auth | MERGED |
| #3 | **P2** RLS permission engine | MERGED (this branch — `rbac-p2-rls-engine` — merged via local conflict-resolution on `HANDOFF.md`, then `gh pr merge 3`) |

`main` now contains P1 + P6a + P2. `gh` installed **and authenticated** (token `repo`). Always `gh pr view <n> --json state` before trusting a "merged" claim (PR #1's first "merged" hadn't actually gone through).

### NEXT: P3 — backend permission enforcement

P3 builds on **merged P2**. Start: `git checkout main && git pull` (verify it has `0007` migration + the `has_platform_perm`/`has_workspace_perm`/`can_manage_role` resolvers + the transition-safe `0003` helper bodies), cut `rbac-p3-backend-enforcement` from `main`, write the P3 plan via `superpowers:writing-plans` (grounded in the merged code), execute via `superpowers:subagent-driven-development` (subagent/task → spec-compliance review → code-quality review → fix loop → commit), final whole-branch review, then `superpowers:finishing-a-development-branch`.

**P3 scope (spec §10):**
- Backend `require_permission()` / `require_workspace_permission()` FastAPI deps replace ALL enum-based authz checks; they call the SAME `0007` resolver functions (single source of truth).
- `/me` returns effective permission keys (platform set + per-workspace map), resolved via the resolvers.
- Onboarding + invite-acceptance **write `user_roles`** (not just enum rows).
- Audit-log writes on every RBAC mutation; privilege-escalation guard (service + DB trigger); single-super_admin invariant enforcement at the service layer.
- **🔒 CRITICAL P2→P3 obligation:** P3 must rewrite the 3 `0007` helper bodies from transition-safe `resolver OR 0003-enum` to **pure resolver**, AND fully reconcile existing `tenant_memberships`/`platform_users` → `user_roles`, **before** any later step drops the enum columns. Dropping enum columns while the legacy disjunct or enum-only principals exist **breaks access**. (Recorded in spec §5 + PR #3 body `docs/superpowers/PR-rbac-p2-body.md`.)

Then P4/P5 (platform & workspace RBAC admin APIs+UIs + audit viewers), P6b (pinned `/me` effective-perms TS contract + legacy adapter + permission-driven nav + two Platform/Workspace shells + workspace switcher), P6c (RBAC admin UIs).

Process discipline (keep it — it caught a P2 spec-level flaw + 8+ plan/code bugs): two-stage review per task; **never trust an implementer's "no regression" claim without independently reproducing at the true baseline**; phases gated on the prior phase being MERGED before the next is planned/executed.

### Spec §5 correction (already applied & merged in P2)

Pure delegation (`is_super_admin → has_platform_perm(...)` alone) is NOT behaviour-preserving in the P2→P3 window — it strands enum-era memberships and locks newly-onboarded owners out (proven: pre-RBAC `tests/rls/` passes at `0006`, fails at pure-`0007`). The merged `0007` uses transition-safe `new_resolver OR original_0003_enum_check` (true superset; honors spec §7.5; instant-revoke for RBAC-granted access). Spec §5 documents this + the P3-retire obligation above.

### Pre-existing `main` debt (NOT from P1/P6a/P2 — flagged, unchanged)

- Managed DB `platform_settings.signups_enabled=true` (operator/smoke leftover) → `tests/routes/test_signup.py::test_signup_status_default_false` + `::test_signup_disabled_returns_403` fail (env-flaky on live DB state; reproduce on `main`). Reset the setting or accept as known.
- 4 ruff `I001` (`scripts/bootstrap.py`, `services/{signup,platform_invites,tenant_invites}.py`); 1 `jose` mypy in `core/auth.py`; 5 frontend `react-refresh` warnings — byte-identical to `main`, zero NEW from any phase.
- Shared-live-DB test isolation: a killed run can orphan rows causing teardown ERRORs in unrelated tests; the session pre-sweep purge fixture self-heals (re-run clean). `make test-clean` forces a purge.

### Operational note (migrations on the shared DB)

`0007` was iterated across subagent tasks; on the live DB each `make migrate` after the first was an alembic no-op (already stamped `0007`). It was reconciled via the migration's own SQL (no alembic-state hand-edit) and the `0006↔0007` round-trip independently re-proven by the P2 gate + final review. A fresh DB applies the complete final `0007` in one pass (ordering verified: resolvers → helpers → policies; downgrade exact inverse). If any env is stuck mid-`0007`: `make migrate-down` to `0006` before pulling, then `make migrate`.

### P2 deferred Minors (non-blocking, optional follow-up)

Optional cleanups noted by code review (none block): extract an `_ephemeral_auth_user()` test helper (~30 dup lines in `tests/rls/test_permission_engine_rls.py`); a one-line comment on the `0007 downgrade()` resolver-drop vs helper-revert asymmetry; module-top `reconcile_rbac` import.

### Conventions in force

`docs/superpowers/ENGINEERING_PRINCIPLES.md`. NO `Co-Authored-By` trailer. Migrations pure raw SQL, reversible, single Alembic head. The `0007` SECURITY DEFINER resolvers are the single source of truth — P3 backend `require_permission()` calls the SAME fns. Test-data hygiene: never create/grant a `super_admin` (P1 single-super_admin partial unique index + `test_no_super_admin_creation` guard forbid it); ephemeral `@example.com` + FK-safe `finally` teardown; positive super_admin via the read-only `existing_super_admin` fixture. `make check` is the merge contract (red ONLY due to the pre-existing `signups_enabled` + ruff baseline above).

### Still USER-DRIVEN, never agent-run

Browser/e2e smokes needing real `.env` + `make dev`/OrbStack + real inboxes.

---

## Durable record

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` (§5 corrected). Plans: `docs/superpowers/plans/2026-05-17-rbac-{p1-schema-foundation,p6a-frontend-shell-and-auth-pages,p2-rls-permission-engine}.md`. PR bodies: `docs/superpowers/PR-rbac-{p1,p6a,p2}-body.md`. Persistent memory at `~/.claude/projects/-Users-jpsingh-Developer-Project-xtrusio/memory/` is machine-local (does NOT travel) — this HANDOFF + spec + plans are the cross-machine record.
