# HANDOFF — RBAC + RLS Re-architecture

**Written:** 2026-05-19
**Status:** **P1, P6a, P2 merged to `main`.** **P3a code-complete + every task two-stage-reviewed + gate green on branch `rbac-p3-backend-enforcement` — NOT yet final-whole-branch-reviewed, NOT yet PR'd.** P3b, P3c, P4/P5, P6b/P6c not started.

Read top to bottom before doing anything.

---

## ⏩ RESUME HERE — 2026-05-19

### PR / branch state

| PR | Phase | State |
|---|---|---|
| #1 | P1 schema foundation | MERGED |
| #2 | P6a frontend shell/auth | MERGED |
| #3 | P2 RLS permission engine | MERGED |
| — | **P3a `user_roles` write-paths & reconciliation** | branch `rbac-p3-backend-enforcement` @ `5af0408`, **pushed? NO — push it (see step 0)**. 0 open PRs. |

`main` @ `48e1470` = P1+P6a+P2. `gh` authenticated. Always `gh pr view <n> --json state` before trusting a "merged" claim.

### NEXT actions (in order)

0. **Push the branch** (it has 6 task commits + plan/handoff, not yet on origin): `git push -u origin rbac-p3-backend-enforcement`.
1. **Final whole-branch P3a review** (opus, like P1/P6a/P2 — this was the next step when we stopped; it was NOT run). It must be SERIALIZED (sole DB user) and `uv run --directory apps/api python -m tests._cleanup` BEFORE any full-suite run (see clean-DB rule below). Assess: behaviour-preservation invariant (zero authz/migration diff vs main), end-to-end idempotency/atomicity, the NOT EXISTS guard, test hygiene, merge-readiness, P3b-precondition satisfied. (A ready-to-use final-review dispatch prompt is in this session's history — the tool call the user interrupted; re-issue it.)
2. **`superpowers:finishing-a-development-branch`** → push (done in step 0) + `gh pr create` for P3a (independent PR; document the deferred Minors + the clean-DB-before-gate rule + that P3a is behaviour-preserving and satisfies the P3b precondition). Then **merge it** (verify via `gh pr view`).
3. **P3b — gated on P3a merge.** After P3a merges: sync `main`, cut `rbac-p3b-…`, `writing-plans` against merged code, `subagent-driven-development`. P3b scope: `core/permissions.py` (`require_permission`/`require_workspace_permission` calling the `0007` resolvers — single source of truth), convert ALL 10 routes + the 3 `tenant_invites` service authz checks from enum→resolver, `/me` returns effective permission keys (platform set + per-workspace map). The P3b precondition (every enum principal has a resolver-visible `user_roles` grant) is **satisfied by P3a** (gate proved `memberships_without_grant 0`, `active_platform_without_grant 0`).
4. **P3c** (after P3b): audit-log writes on RBAC mutations; privilege-escalation guard (service + DB trigger); single-super_admin Python enforcement; migration `0008` retiring the transition-safe `OR 0003-enum` disjunct → pure resolver. **🔒 CRITICAL ORDER:** the enum columns may be dropped ONLY after (a) P3a write-paths + reconcile populate `user_roles` for all principals [done], (b) P3b makes the backend resolver-authoritative, (c) P3c rewrites the `0007` helper bodies to pure-resolver. Dropping enum columns earlier breaks access (spec §5).
5. Then P4/P5 (platform & workspace RBAC admin APIs+UIs + audit viewers), P6b (pinned `/me` effective-perms TS contract + legacy adapter + permission-driven nav + two Platform/Workspace shells + workspace switcher), P6c (RBAC admin UIs).

### What P3a delivered (branch `rbac-p3-backend-enforcement`, behaviour-preserving — ZERO authz decision changed; enum still authoritative)

- `rbac/grants.py::grant_role()` — idempotent resolve-role + `user_roles` INSERT ON CONFLICT DO NOTHING, NULL-safe, raises `LookupError`, no internal commit.
- `rbac/reconcile.py` += `wire_workspace_role_perms(db,*,workspace_id)` (scoped, no-commit, one workspace's role_permissions) and `reconcile_user_roles_from_enums(db)` (Step A: idempotently seed missing per-tenant workspace role ROWS for ALL tenants + per-tenant wire; Step B: platform backfill WITH a `NOT EXISTS` guard [Postgres NULL-distinctness makes `ON CONFLICT(composite)` inert for workspace_id-NULL platform rows; the single-super_admin index is an expression partial index ON CONFLICT can't arbitrate], then tenant_memberships backfill; ONE commit). `reconcile_rbac`/`_sync_role_perms` byte-unchanged.
- onboarding: ONE atomic commit — seed new tenant's 4 system roles (0006-friendly tuples) → scoped `wire_workspace_role_perms` → `grant_role(owner)`; NO global reconcile on the request path (fixed in commit `3ee7723`).
- invite-acceptance (`_accept_platform` admin-only; `_accept_tenant` all roles): `grant_role` in the SAME txn as the enum write, before the existing `IntegrityError→AlreadyProvisionedError` commit (idempotent re-accept preserved).
- bootstrap: grants platform `super_admin`; `--force` clears the stale `user_roles …00a1` grant before recreating (single-super_admin global-singleton invariant upheld across force/non-force/crash/re-run).
- startup hook (`main.py`) + `__main__.py`/`make rbac-seed` run BOTH reconcilers (best-effort, boot-safe).
- 6 task commits: `739cd03` (grant_role), `3ef8d12`+`3ee7723` (onboarding+fix), `1429269` (invites), `cfb0217` (bootstrap), `3dd01fe` (reconcile). Gate: **clean-DB full suite 130 passed / 2 documented vacuous skips / 0 failed**; `git diff main...HEAD` for routes/core/auth.py/tenant_invites authz = EMPTY; no migration; single head `0007`.

### ⚠️ Clean-DB-before-gate rule (firmly established)

The shared managed DB has a known fragility: a test failing before its `finally` mid-run orphans ephemeral rows → false failures in later count-based tests. **Always `uv run --directory apps/api python -m tests._cleanup` before any full-suite gate/review run, and run suites serialized (one DB-touching agent at a time).** A clean purge cascade-cleans ephemeral RBAC rows via the tenant/auth.users `ON DELETE CASCADE`. Verified: from a clean DB the P3a suite is 0-failed; the only "failures" ever seen were transient mid-run pollution, not real.

### Accepted deferred P3a Minors (non-blocking; address opportunistically or in P3b/P3c)

- `scripts/bootstrap.py` call-site: add a one-line comment that a crash before the grant commit is self-healed by the Task-5 reconcile.
- `rbac/reconcile.py` docstring: "byte-identical to 0006 mapping" → "semantically equivalent (adds defensive `is_system`; result set unchanged)".
- New rbac tests: optional teardown-via-`ON DELETE CASCADE` simplification (delete the ephemeral tenant/auth.users; let cascade drive the rest).
- `reconcile_user_roles_from_enums` O(tenants) per-tenant wire loop on every boot/`make rbac-seed` — fine for the P3a horizon; future optimization watch-item.

### Pre-existing `main` debt (NOT from any phase — flagged, unchanged)

- Managed DB `platform_settings.signups_enabled` live state → `tests/routes/test_signup.py::{test_signup_status_default_false,test_signup_disabled_returns_403}` env-flaky (pass or fail by state; reproduce on main).
- 4 ruff `I001` (`scripts/bootstrap.py`, `services/{signup,platform_invites,tenant_invites}.py`); 1 `jose` mypy in `core/auth.py`; frontend `react-refresh` warnings — byte-identical to main, zero NEW from any phase.
- Memory `deferred-review-fixes-pending-p3` — a parked backlog (CI, pagination, signup, JWKS, etc.) gated until RBAC P3 fully merges; do NOT start those early.

### Conventions in force

`docs/superpowers/ENGINEERING_PRINCIPLES.md`. NO `Co-Authored-By`. Migrations pure raw SQL, reversible, single Alembic head. The `0007` SECURITY DEFINER resolvers are the single source of truth — P3b `require_permission()` calls the SAME fns. Test-data hygiene: never create/grant a `super_admin` (P1 single-super_admin partial unique index + `tests/test_no_super_admin_creation.py` guard which greps test files); ephemeral `@example.com` + FK-safe `finally` teardown; positive super_admin via the read-only `existing_super_admin` fixture. Process discipline (caught a P2 spec flaw + a P3a plan-SQL flaw + 10+ bugs): two-stage review/task; never trust an implementer "no regression" claim without independently reproducing at the true baseline; phases gated on the prior phase being MERGED before the next is planned/executed; serialized DB access + `_cleanup` before gates.

### Still USER-DRIVEN, never agent-run

Browser/e2e smokes needing real `.env` + `make dev`/OrbStack + real inboxes.

---

## Durable record

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` (§5 corrected). Plans: `docs/superpowers/plans/2026-05-17-rbac-{p1,p6a,p2}-*.md`, `docs/superpowers/plans/2026-05-18-rbac-p3a-user-roles-write-paths.md` (amended). PR bodies: `docs/superpowers/PR-rbac-{p1,p6a,p2}-body.md` (write a P3a one at finishing). Persistent memory at `~/.claude/projects/-Users-jpsingh-Developer-Project-xtrusio/memory/` is machine-local (does NOT travel) — this HANDOFF + spec + plans are the cross-machine record.
