# HANDOFF — RBAC + RLS Re-architecture

**Written:** 2026-05-19, updated 2026-05-23 (P6c Slice 1 merged)
**Status:** **Backend RBAC re-architecture + Platform/Workspace RBAC admin + Frontend permission-driven shells + Platform/Workspace Roles CRUD UI COMPLETE & merged** — P1, P2, P3a, P3b, P3c, P6a, P3.5, type-the-tests, P4, P5, P6b, P6c Slice 1 all in `main` (`bdfc39b`). The enum→resolver authorization cutover is finished, platform + workspace RBAC admin APIs are live, **the frontend consumes the pinned `/me` effective-perms contract with permission-driven nav across two physically-separate Platform/Workspace shells**, and **super_admins + workspace owners can now create/edit/delete custom roles via the new `/platform/roles` and `/workspace/$wid/roles` UIs**. Remaining: P6c Slices 2 + 3 (Audit log viewers + Members invite-port + nav additions + cleanup); P6d (grant-management UIs + missing list endpoints + workspace settings); late enum-column cleanup once every backend enum read is gone.

Read top to bottom before doing anything.

---

## 🌙 SLEEPING — RESUME TOMORROW (written 2026-05-23, 03:30 local)

The user signed off mid-session. **Start tomorrow by reading this section before doing anything else.**

### Where we left off

- **Slice 1 (Roles CRUD) MERGED** — PR #18 squashed to `main`. HANDOFF updated. Branch `rbac-p6c-slice-1-roles-crud` still on origin (can be deleted after Slice 2 ships).
- **Slice 2 (Audit log) IN FLIGHT** — a background Opus subagent was running on branch `rbac-p6c-slice-2-audit-log` in the main checkout (`/Users/jpsingh/Developer/Project/xtrusio`). When the user signed off, **all 13 expected files were written** (modifications + new), and the subagent was running the vitest gate. It had NOT committed yet.
- **Slice 3 (Members + nav + cleanup) NOT STARTED** — first dispatch (in a sibling worktree `/Users/jpsingh/Developer/Project/xtrusio-slice-3`) was blocked by harness path scope. Branch `rbac-p6c-slice-3-members-cleanup` exists locally but has zero work on it beyond Slice 2's base.

### Tomorrow's first checks (in this order)

1. `cd /Users/jpsingh/Developer/Project/xtrusio && git branch --show-current` — should be `rbac-p6c-slice-2-audit-log` (the subagent's working branch). If it's a different branch the subagent's writes are at risk; investigate before doing anything else.
2. `git status` — if Slice 2's files are still uncommitted (the list below should match), the subagent died or stalled. If they're all committed in one or two new commits ahead of Slice 1, Slice 2 finished — proceed to step 5.
3. Check for any leftover vitest / node / pytest processes from the subagent and kill if hung: `ps aux | grep -iE 'vitest|pytest|node.*xtrusio' | grep -v grep`.
4. **If Slice 2 is uncommitted:** re-dispatch an Opus subagent to finish — same prompt as before, with the addendum "all 13 files are already written on disk; just run the gate and commit. Don't rewrite files unless something is broken." OR you can simply `git add` + commit yourself after running `pnpm --filter @xtrusio/web exec vitest run src/components/audit/ src/components/platform-audit-log-page.test.tsx src/components/workspace-audit-log-page.test.tsx` + `pnpm --filter @xtrusio/web typecheck`.
5. **Once Slice 2 is committed:** push branch, open PR, squash-merge per the convention. PR body file location: `docs/superpowers/PR-rbac-p6c-slice-2-body.md` (does not exist yet — write one mirroring `docs/superpowers/PR-rbac-p6c-slice-1-body.md`'s shape from PR #18).
6. **Update HANDOFF** to mark Slice 2 merged (move it into the Done & merged table) and pivot NEXT to Slice 3.
7. **Then Slice 3:** rebase `rbac-p6c-slice-3-members-cleanup` onto the new main (`git fetch && git rebase origin/main`), then dispatch ONE Opus subagent for the whole slice per `docs/superpowers/plans/2026-05-22-rbac-p6c-slice-3-members-and-cleanup.md`. **Do NOT use a sibling worktree** — the harness blocks subagent access outside the main checkout. Work in `/Users/jpsingh/Developer/Project/xtrusio` directly (you'll need Slice 2 merged first so this checkout is on a clean branch).

### Slice 2 working-tree inventory (what should be uncommitted on `rbac-p6c-slice-2-audit-log` if the subagent died)

Modified:
- `apps/api/src/xtrusio_api/schemas/audit_log.py` (+`actor_email: str | None`)
- `apps/api/src/xtrusio_api/services/platform_audit_log.py` (+LEFT JOIN auth.users)
- `apps/api/src/xtrusio_api/services/workspace_audit_log.py` (+LEFT JOIN auth.users)
- `apps/api/tests/services/test_platform_audit_log.py` (+3 actor_email tests)
- `apps/api/tests/services/test_workspace_audit_log.py` (+3 actor_email tests)
- `apps/web/src/lib/api.ts` (+2 audit fetchers)
- `apps/web/src/routeTree.gen.ts` (auto-regenerated)
- `apps/web/src/routes/_app.workspace.$workspaceId.audit-log.tsx` (full rewrite — replaces placeholder)
- `packages/api-types/src/index.ts` (+1 re-export line)

New:
- `apps/web/src/components/audit/{load-more-button,audit-table,audit-detail-drawer}.tsx` + matching `.test.tsx` files
- `apps/web/src/components/{platform,workspace}-audit-log-page.tsx` + matching `.test.tsx` files
- `apps/web/src/routes/_app.platform.audit-log.tsx`
- `packages/api-types/src/audit-log.ts`

Also on disk in `/Users/jpsingh/Developer/Project/xtrusio` (NOT yet committed anywhere):
- `docs/superpowers/PR-rbac-p6c-slice-1-body.md` — already used to set PR #18's body; can be committed to `main` separately whenever.
- `.claude/settings.json` modified (some harness-level setting change; review before committing).
- `.claude/ralph-loop.local.md` untracked (Ralph loop state file from Slice 1's loop run — should be gitignored; deletable).

### Worktrees in play

- `/Users/jpsingh/Developer/Project/xtrusio` — main checkout, currently on `rbac-p6c-slice-2-audit-log`.
- `/Users/jpsingh/Developer/Project/xtrusio-slice-1` — secondary worktree on `main` (used to write this HANDOFF). Keep or `git worktree remove ../xtrusio-slice-1` if no longer needed.
- `/Users/jpsingh/Developer/Project/xtrusio-slice-3` — secondary worktree on `rbac-p6c-slice-3-members-cleanup` (empty branch). The harness blocks subagent access here — **do not try to dispatch Slice 3 into this worktree again**. Either delete the worktree (`git worktree remove ../xtrusio-slice-3 && git branch -D rbac-p6c-slice-3-members-cleanup`) and recreate the branch later in the main checkout, OR leave the worktree but ignore it for subagent dispatches.

### What changed in CLAUDE.md mid-session that needs to stay

The execution-cadence section was rewritten to "ONE Opus subagent for the whole slice + 'ship it'" — the 4-chunk approach used in Slice 1 was overkill. Slice 2 + 3 follow the new pattern (one subagent each, no chunks, no per-task tracking, no spec-reviewer, no code-quality-reviewer subagents except for high-risk slices). This commit pulls that CLAUDE.md update onto `main` so it's authoritative for tomorrow.

---

## ⏩ RESUME HERE — 2026-05-23

### Done & merged (PRs #1–#6, #8, #10, #11, #13–#16, #18 MERGED; `main` @ `bdfc39b`; single Alembic head `0009`; 0 open PRs)

| Phase | What |
|---|---|
| P1 (#1) | RBAC schema: `permissions/roles/role_permissions/user_roles/rbac_audit_log`, code catalog, reconciler, system-role seeds, single-super_admin index, enum backfill |
| P2 (#3) | `0007` SECURITY DEFINER resolvers `has_platform_perm`/`has_workspace_perm`/`can_manage_role`; `0003` helpers → transition-safe `resolver OR 0003-enum` |
| P3a (#4) | `grant_role`; onboarding/invite-accept/bootstrap write `user_roles`; `reconcile_user_roles_from_enums` (+ startup/`make rbac-seed` wiring) — every principal resolver-visible |
| P3b (#5) | `core/permissions.py` (`require_permission` calling the resolvers); all 10 routes + tenant-invite service authz converted enum→resolver; `/me` additive effective-perm keys |
| P3c (#6) | `0008`: helpers → **pure resolver** (enum disjunct retired, reversible); pre-RBAC rls canaries reframed to grants. **Cutover complete.** |
| P6a (#2) | Frontend: pathless `_app` shell (shell-bleed fixed), shared `AuthLayout`, auth-page polish, public `/api/signup-status` rename |
| P3.5 (#8) | Review-fix backlog: CI workflow (`.github/workflows/ci.yml`), cursor pagination on 3 list endpoints + structural invariant test, JWKS coalescing lock, signup duplicate-email by `AuthApiError` class, lifespan fail-fast (`STARTUP_RECONCILE_TOLERANT` escape hatch), AuthGuard duplicate-staleTime cleanup. Principles §8 amended to permit managed-Supabase test project. |
| type-the-tests (#10) | Annotated 10 P3a/P3b-era test files for `mypy --strict`; project-wide `ruff format` cleanup. `make check` now fully green on `main` — was the prerequisite for P4. |
| P4 (#11) | **Platform RBAC admin (API + governance).** Migration `0009` adds DB triggers (privilege-escalation, immutable platform-system-roles); `core/audit.py` writes one row per RBAC mutation. `GET/POST/PATCH/DELETE /api/platform/roles[/{id}]` for custom platform-role CRUD (gated by `platform.roles.manage`). `GET/POST/DELETE /api/platform/users/{user_id}/roles[/{grant_id}]` for grants (gated by `platform.users.read/manage`). `GET /api/platform/audit-log` (gated by `platform.audit.read`). Service-layer enforcement of privilege-escalation + single-super_admin invariant mirrors DB triggers for friendly 403/409 errors. **Backend only — UI deferred to P6c per scope split.** |
| P5 (#13) | **Workspace RBAC admin (API only).** Per-workspace mirror of P4 surface, scope-isolated to one `workspace_id`. `GET/POST/PATCH/DELETE /api/workspaces/{wid}/roles[/{id}]` for custom workspace-role CRUD (gated by `workspace.roles.manage`). `GET/POST/DELETE /api/workspaces/{wid}/members/{uid}/roles[/{grant_id}]` for grants (`workspace.members.read`/`workspace.members.manage`). `GET /api/workspaces/{wid}/audit-log` (gated by `workspace.audit.read`). Service-layer enforces (1) `tenant_memberships` pre-check, (2) per-workspace privilege-escalation pre-check (friendly 403 before the `0009` DB trigger), (3) **≥1-active-owner floor on revoke** (no DB trigger covers this — service is the sole guard, 409 `owner_floor`). Workspace-system-role immutability is service-layer-only too — `0009.reject_system_role_mutation` deliberately scopes to `scope='platform'` (lines 119–120 with comment at 102–109). Reuses `core/audit.py` + cursor codec from `services.platform_audit_log` + `core/pagination.py`. **Backend only — UI deferred to P6c per scope split.** |
| P6c Slice 1 (#18) | **Frontend Roles CRUD UI (platform + workspace) + permissions-catalog endpoint.** New `GET /api/permissions/catalog` (authenticated, no perm gate, serialises static `CATALOG`) at `apps/api/src/xtrusio_api/routes/permissions.py` with 5 route tests. TS mirrors in `@xtrusio/api-types` (`permission.ts`, `role.ts`). Central `qk` TanStack Query key registry at `apps/web/src/lib/query-keys.ts`. Six shared UI blocks under `apps/web/src/components/{forbidden,roles/*}` (`<Forbidden>`, `<PermissionPicker>` grouped by `category` with per-category select-all, `<RoleFormDialog>` with key-disabled-in-edit + inline footer error, `<RolesTable>` with `is_system` badge + hidden actions, `<DeleteRoleDialog>` with cascade warning copy). Per-scope pages: `<PlatformRolesPage>` at `/platform/roles` (gated `platform.roles.manage`) and `<WorkspaceRolesPage workspaceId>` at `/workspace/$wid/roles` (gated `workspace.roles.manage`, replaces P6b placeholder). New `apps/web/src/components/ui/checkbox.tsx` via shadcn CLI. 11 new error-message mappings (incl. prefix-handlers for `unknown_permission:<key>` / `privilege_escalation:<perm>`; pre-maps P6d codes too). Pre-existing ruff isort cleanup on `services/{platform_invites,signup,tenant_invites}.py` + `scripts/bootstrap.py`. No migration. **Backend `GET /api/platform/users` / `GET /api/workspaces/{wid}/members` deliberately deferred to P6d, so grant-management UI also deferred.** End-of-phase backend `make check` deliberately deferred by user — frontend vitest green pre-merge (12 new component tests pass; total web vitest will be 86+); api-types + web typecheck green; ruff + format check green; backend pytest grinding at merge time (will be re-validated at end of P6c Slice 3). |
| P6b (#16) | **Frontend permission-driven nav + Platform/Workspace shells + workspace switcher.** Pinned `/me` TS contract in `packages/api-types/src/me.ts` (mirrors `apps/api/.../schemas/me.py:MeResponse` 1:1 with additive `platform_permissions` + `tenants[].permissions`); legacy-compat adapter at `apps/web/src/lib/me-adapter.ts` (`hasPlatformPerm`/`hasWorkspacePerm`/`findTenant`/`getDefaultLandingPath`/`useMe`). `_app.tsx` reduced to a pass-through; two physically-separate shells live in `_app.platform.tsx` (5 existing platform pages `git mv`'d under `_app.platform.*`) and `_app.workspace.$workspaceId.tsx` (5 placeholder children: index/members/roles/audit-log/settings, each rendering real `PageHeader` + `EmptyState`). `nav.ts` items gained `required_perm`; `PlatformSidebar` + `WorkspaceSidebar` filter via the adapter. `WorkspaceSwitcher` dropdown lists `me.tenants[]` + "Platform admin" (gated on `me.platform`), navigates on selection, persists last-selected to `localStorage` (`xtrusio.last-workspace` + `__platform__` sentinel). `resolveRoute('/')` honours `readLastWorkspace()`. **AuthGuard bug fix:** switched from `useRouter().state.location.pathname` (non-reactive) to `useRouterState({select: s => s.location.pathname})` so re-renders fire after `navigate()` — the new aggressive resolver exposed the stale-pathname bug that the old, less-aggressive resolver had masked. 74/74 web vitest pass (was 39); api-types + web typecheck green. **Frontend nav/shells only — RBAC admin UI bodies still deferred to P6c.** |

Backend authorization is now **fully resolver/permission-driven** at both platform AND workspace scope, and consistent with RLS (same `0007` fns). Verified: full suite green from a CLEAN DB (279 passed; 0 failed; 3 documented vacuous skips; env-flaky `test_signup` state-dependent), `0007↔0008↔0009` reversible. Frontend is now permission-keys-driven for nav/shells with the enum fields kept additively on `MeResponse` (LATE cleanup item) so per-page enum→permission migration in P6c is non-blocking.

### NEXT (gated: each phase planned/executed only after the prior MERGED)

1. ~~**P4**~~ — DRAINED by #11 (merged 2026-05-20). Platform-side RBAC admin API + governance triggers in place. Plan at `docs/superpowers/plans/2026-05-20-rbac-p4-platform-admin.md`.
2. ~~**P5**~~ — DRAINED by #13 (merged 2026-05-21). Workspace-side RBAC admin API in place. Plan at `docs/superpowers/plans/2026-05-21-rbac-p5-workspace-admin.md`. PR body at `docs/superpowers/PR-rbac-p5-body.md`.
3. ~~**Deferred-from-P3c governance**~~ — DRAINED by #11. Audit-log writes are live (`core/audit.py`); priv-escalation guard is enforced at both service layer (P4 + P5) and DB trigger (`0009` — covers platform + workspace scope via `has_workspace_perm` dispatch); single-super_admin invariant has both the DB partial-unique index (P1) and the service-layer friendly check (P4 `services/platform_role_grants.py`); ≥1-workspace-owner floor enforced at service layer (P5 `services/workspace_role_grants.py`).
4. ~~**P6b**~~ — DRAINED by #16 (merged 2026-05-22). Pinned `/me` contract + adapter + permission-driven nav + Platform/Workspace shells + workspace switcher live on `main`. Plan at `docs/superpowers/plans/2026-05-21-rbac-p6b-frontend-shells.md`. PR body at `docs/superpowers/PR-rbac-p6b-body.md`. **End-of-phase `make check` was deliberately deferred by the user** — controller-run gate to be completed off-band (lint + typecheck already passed pre-merge; pytest backend untouched in P6b so expected green).
5. ~~**P6c Slice 1**~~ — DRAINED by #18 (merged 2026-05-23). Platform + Workspace Roles CRUD UI + `GET /api/permissions/catalog` live. Plan at `docs/superpowers/plans/2026-05-22-rbac-p6c-slice-1-roles-crud.md`. PR body at `docs/superpowers/PR-rbac-p6c-slice-1-body.md`. Spec for the whole P6c at `docs/superpowers/specs/2026-05-22-rbac-p6c-admin-uis-design.md` (§3 maps the scope split).
6. **P6c Slice 2 — next gated step** (currently being implemented by a background Opus subagent on branch `rbac-p6c-slice-2-audit-log`). Audit log viewers (platform + workspace) + `AuditEventOut.actor_email` LEFT JOIN onto `auth.users`. Three shared UI blocks (`<AuditTable>`, `<AuditDetailDrawer>`, `<LoadMoreButton>`); per-scope pages at `/platform/audit-log` and `/workspace/$wid/audit-log` (replaces P6b placeholder). No migration. Plan at `docs/superpowers/plans/2026-05-22-rbac-p6c-slice-2-audit-log.md`.
7. **P6c Slice 3** (queued after Slice 2 ships). Workspace Members invite-only port from `tenant-users-page` (member list deferred to P6d), platform nav gains Roles + Audit log items, `UserMenu` rewrite (drop local `Me` type + duplicate `useQuery(['me'])`), `tenant-users-page` `canInvite` switches to `hasWorkspacePerm`. Pure frontend. Plan at `docs/superpowers/plans/2026-05-22-rbac-p6c-slice-3-members-and-cleanup.md`.
8. **P6d** (after all of P6c merges). Backend gaps: `GET /api/platform/users`, `GET /api/workspaces/{wid}/members`, `GET/PUT /api/workspaces/{wid}/settings`. Plus the grant-management UIs (platform + workspace) and the workspace Settings UI that depend on those endpoints. Possibly a tiny `GET /api/.../roles/{id}/grants?count_only` so the role-delete dialog can show a precise count.
6. **🔒 LATE cleanup (only after P6c removes ALL frontend enum consumption AND every backend enum read is gone):** drop `platform_users.role` / `tenant_memberships.role` columns + the `platform_role`/`tenant_role` enum types. Do NOT do this earlier — `/me` (P3b additive), onboarding/invite-accept/bootstrap still legitimately write the enum rows; `0008` downgrade restores the enum-reading OR-form so the enum columns must exist while `0008` is reversible.
7. ~~**Parked review-fix backlog NOW UNBLOCKED**~~ — **DRAINED by P3.5 (#8) + type-the-tests (#10) + P4 (#11)**. Remaining surfaced follow-ups (captured for a future phase):
   - ~~Pre-existing test-file typecheck debt~~ — DRAINED by #10. `uv run mypy apps/api` now reports `Success: no issues found`.
   - **`gotrue` → `supabase_auth` migration:** supabase-py 2.x emits a `DeprecationWarning` saying `gotrue` is being replaced by `supabase_auth`. Migrate imports in a future phase. Touches `services/signup.py` (the `from gotrue.errors import AuthApiError`).
   - **Pre-existing broad `except Exception` in invite services:** `services/platform_invites.py:90` and `services/tenant_invites.py:146` swallow every exception class into `EmailProviderUnavailableError`. Narrow to specific (`httpx.HTTPError`, `AuthApiError`, `AuthRetryableError`, etc.) in a follow-up audit.
   - **`grant_role` (`rbac/grants.py`) `ON CONFLICT DO NOTHING` + Postgres NULLS DISTINCT:** for `workspace_id IS NULL` platform grants, the unique constraint doesn't match — duplicate INSERTs would silently produce duplicate rows. **Existing call sites are safe in practice** (reconciler uses `NOT EXISTS`; onboarding/invite-accept/bootstrap are once-per-user paths). P4's `grant_platform_role` and P5's `grant_workspace_role` services both use an explicit `SELECT then INSERT`. Follow-up: migrate `user_roles` to `UNIQUE NULLS NOT DISTINCT (auth_user_id, role_id, workspace_id)` (PG15+), or backport the explicit SELECT pattern.
   - **`DELETE /api/platform/users/{user_id}/roles/{grant_id}`** doesn't verify `grant.auth_user_id == user_id`. `grant_id` is globally unique so a mismatched user_id in the path is harmless, but adding the check would be a small consistency polish (P4 follow-up). P5's workspace DELETE already does this — it pins on `(id, user_id, workspace_id)` as load-bearing scope isolation.
   - **P5 `grant_workspace_role` concurrent-duplicate-grant race:** explicit pre-SELECT + INSERT (no ON CONFLICT). Two concurrent identical grants → one wins, the other raises IntegrityError → 5xx. Acceptable today (workspace.members.manage is rare; concurrent identical grants ≈ zero); future hardening: `INSERT ... ON CONFLICT DO NOTHING RETURNING ...` with a fallback SELECT. Documented in `services/workspace_role_grants.py:grant_workspace_role` docstring.
   - **P6b deferred end-of-phase `make check`:** lint + ruff format + mypy --strict + turbo typecheck + frontend vitest (74/74) all passed pre-merge. The full backend `pytest apps/api/tests` was deliberately deferred by the user; P6b touched zero backend code, so backend should still be green from the P5-era CLEAN-DB run (279 passed). User to confirm via `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check` at convenience.
   - **AuthGuard stale-pathname bug (LATENT on main pre-P6b):** `useRouter().state.location.pathname` doesn't subscribe to router state changes, so a `navigate()` from inside the guard left it reading the stale pathname. Masked on main by the less-aggressive pre-P6b resolver; P6b's new resolver made it surface. **Already fixed in P6b** by switching to `useRouterState({select: s => s.location.pathname})`. Document only — no follow-up action required.

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

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` (§5 corrected for transition-safe→pure-resolver). Plans: `docs/superpowers/plans/2026-05-1{7,8,9}-rbac-*.md` (P1, P6a, P2, P3a, P3b, P3c), `docs/superpowers/plans/2026-05-20-rbac-p4-platform-admin.md`, `docs/superpowers/plans/2026-05-20-type-the-tests.md`, `docs/superpowers/plans/2026-05-21-rbac-p5-workspace-admin.md`. PR bodies: `docs/superpowers/PR-rbac-{p1,p6a,p2,p3a,p3b,p5}-body.md` (+ P3c body inline in PR #6, P4 in PR #11, type-the-tests in PR #10). Persistent memory at `~/.claude/projects/-Users-jpsingh-Developer-Project-xtrusio/memory/` is machine-local (does NOT travel) — this HANDOFF + spec + plans are the cross-machine record.
