# HANDOFF — RBAC + RLS Re-architecture

**Written:** 2026-05-19, updated 2026-05-23 (P6c + P6d MERGED + polish round MERGED — RBAC admin surface complete; foundation ready for first product feature).
**Status:** **Backend RBAC re-architecture + Platform/Workspace RBAC admin + Frontend permission-driven shells + Platform/Workspace Roles CRUD UI + Audit log viewers + Workspace Members surface + Grant-management UIs + Workspace Settings UI + post-merge polish all COMPLETE & merged** — P1, P2, P3a, P3b, P3c, P6a, P3.5, type-the-tests, P4, P5, P6b, P6c (Slices 1+2+3), P6d (backend + frontend), and two polish PRs all in `main` (`564b11e`). The enum→resolver authorization cutover is finished; backend admin APIs are live; the frontend has permission-driven nav across two physically-separate Platform/Workspace shells; super_admins and workspace owners can do **every** RBAC admin action through the UI (list users/members, create/edit/delete roles, grant/revoke roles, read audit logs, rename workspaces); grant races are hardened. **The admin surface is complete; next phase is the first product feature.**

Read top to bottom before doing anything.

---

## ⏩ RESUME HERE — 2026-05-23 (post-P6d)

### Done & merged (PRs #1–#6, #8, #10, #11, #13–#16, #18–#24 MERGED; `main` @ `564b11e`; single Alembic head `0009`; 0 open PRs)

| Phase | What |
|---|---|
| P1 (#1) | RBAC schema: `permissions/roles/role_permissions/user_roles/rbac_audit_log`, code catalog, reconciler, system-role seeds, single-super_admin index, enum backfill |
| P2 (#3) | `0007` SECURITY DEFINER resolvers `has_platform_perm`/`has_workspace_perm`/`can_manage_role`; `0003` helpers → transition-safe `resolver OR 0003-enum` |
| P3a (#4) | `grant_role`; onboarding/invite-accept/bootstrap write `user_roles`; `reconcile_user_roles_from_enums` (+ startup/`make rbac-seed` wiring) — every principal resolver-visible |
| P3b (#5) | `core/permissions.py` (`require_permission` calling the resolvers); all 10 routes + tenant-invite service authz converted enum→resolver; `/me` additive effective-perm keys |
| P3c (#6) | `0008`: helpers → **pure resolver** (enum disjunct retired, reversible); pre-RBAC rls canaries reframed to grants. **Cutover complete.** |
| P6a (#2) | Frontend: pathless `_app` shell (shell-bleed fixed), shared `AuthLayout`, auth-page polish, public `/api/signup-status` rename |
| P3.5 (#8) | Review-fix backlog: CI workflow (`.github/workflows/ci.yml`), cursor pagination on 3 list endpoints + structural invariant test, JWKS coalescing lock, signup duplicate-email by `AuthApiError` class, lifespan fail-fast (`STARTUP_RECONCILE_TOLERANT` escape hatch), AuthGuard duplicate-staleTime cleanup. Principles §8 amended to permit managed-Supabase test project. |
| type-the-tests (#10) | Annotated 10 P3a/P3b-era test files for `mypy --strict`; project-wide `ruff format` cleanup. `make check` fully green on `main`. |
| P4 (#11) | **Platform RBAC admin (API + governance).** Migration `0009` adds DB triggers (privilege-escalation, immutable platform-system-roles); `core/audit.py` writes one row per RBAC mutation. `GET/POST/PATCH/DELETE /api/platform/roles[/{id}]`. `GET/POST/DELETE /api/platform/users/{user_id}/roles[/{grant_id}]`. `GET /api/platform/audit-log`. Service-layer enforcement mirrors DB triggers for friendly 403/409 errors. |
| P5 (#13) | **Workspace RBAC admin (API only).** Per-workspace mirror of P4 surface, scope-isolated to one `workspace_id`. `GET/POST/PATCH/DELETE /api/workspaces/{wid}/roles[/{id}]`. `GET/POST/DELETE /api/workspaces/{wid}/members/{uid}/roles[/{grant_id}]`. `GET /api/workspaces/{wid}/audit-log`. Service-layer ≥1-active-owner floor + per-workspace privilege-escalation pre-check + workspace-system-role immutability. |
| P6b (#16) | **Frontend permission-driven nav + Platform/Workspace shells + workspace switcher.** Pinned `/me` TS contract (`packages/api-types/src/me.ts`); legacy-compat adapter (`apps/web/src/lib/me-adapter.ts`); two physically-separate shells (`_app.platform.tsx`, `_app.workspace.$workspaceId.tsx`); `nav.ts` items gained `required_perm`; `WorkspaceSwitcher` dropdown lists `me.tenants[]` + "Platform admin"; `localStorage` last-selected workspace; AuthGuard stale-pathname bug fixed. |
| P6c Slice 1 (#18) | **Frontend Roles CRUD UI (platform + workspace) + permissions-catalog endpoint.** `GET /api/permissions/catalog`. Six shared UI blocks (`<Forbidden>`, `<PermissionPicker>` grouped by category, `<RoleFormDialog>` with key-disabled-in-edit, `<RolesTable>` with `is_system` badge, `<DeleteRoleDialog>` with cascade warning, `ui/checkbox`). Per-scope pages `<PlatformRolesPage>` + `<WorkspaceRolesPage>` (gated `platform.roles.manage` / `workspace.roles.manage`). Central `qk` TanStack Query key registry; 11 error-message mappings. |
| P6c Slice 2 (#19) | **Audit log viewers (platform + workspace).** `AuditEventOut` gains `actor_email: str \| None` via service-layer LEFT JOIN onto `auth.users`. Shared UI blocks: `<AuditTable>` (dense `[time \| actor email \| action \| target]`), `<AuditDetailDrawer>` (Sheet, pretty-printed before/after JSON), `<LoadMoreButton>` (hidden when `next_cursor === null`). Per-scope pages `<PlatformAuditLogPage>` + `<WorkspaceAuditLogPage>` (gated `platform.audit.read` / `workspace.audit.read`). Cursor-driven Load-more with local accumulator (deliberately not `useInfiniteQuery`). No migration. |
| P6c Slice 3 (#20) | **Workspace Members port + platform nav + cleanup.** `<WorkspaceMembersPage>` invite-only port from `tenant-users-page` (gated `workspace.members.read` page + `workspace.members.invite` button); Slice-3 originally shipped a "members list ships in P6d" notice, since superseded by P6d's list section. `platformNav` gains Roles + Audit log entries. `<UserMenu>` rewrite consumes `useMe()` from me-adapter (drops legacy `type Me` + duplicate inline `useQuery(["me"])`). `tenant-users-page` `canInvite` switches from enum to `hasWorkspacePerm`. Workspace Settings placeholder copy updated. |
| P6d backend (#21) | **List endpoints + workspace settings.** `GET /api/platform/users` (cursor-paginated; gated `platform.users.read`; includes `granted_role_count`). `GET /api/workspaces/{wid}/members` (cursor-paginated; gated `workspace.members.read`; LEFT JOIN auth.users for email). `GET/PUT /api/workspaces/{wid}/settings` (gated `workspace.settings.read` / `workspace.settings.manage`; PUT writes audit-log row ONLY when `name` actually changed; MVP allows only `name` mutation). TS mirrors + re-exports. Mechanical ruff isort cleanup on 4 pre-existing files. No migration; Alembic head stays at `0009`. Catalog perms `workspace.settings.{read,manage}` already existed from P5 — plan section A.1 was a no-op. |
| P6d frontend (#22) | **Grant-management UIs + workspace settings + platform users list.** Shared `<RolePicker>` + `<GrantManagerDialog>` (Sheet; discriminated union on scope; revokes + grants with `qk` invalidation for parent list re-render). `<PlatformUsersPage>` at `/platform/users` (gated `platform.users.read`). `<WorkspaceMembersListPage>` embedded under Slice-3's invite UI at `/workspace/$wid/members` (gated `workspace.members.read` + `workspace.members.manage`). `<WorkspaceSettingsPage>` at `/workspace/$wid/settings` (gated `workspace.settings.{read,manage}`; Save disabled when name unchanged). 6 P4/P5 grant fetchers added to `lib/api.ts`; 7 new `qk` entries; 3 new error mappings. |
| Polish round 1 (#23) | **Orphaned UI removal + exception narrowing + DELETE consistency.** Dropped orphaned `users-page.tsx` (the pre-P6d platform-invites UI; backend endpoints intact for future use). Narrowed `except Exception` in `services/{platform_invites,tenant_invites}.py` to `(AuthApiError, AuthRetryableError, httpx.HTTPError)`. `DELETE /api/platform/users/{user_id}/roles/{grant_id}` now validates `grant.auth_user_id == user_id` (404 on mismatch — parity with P5 workspace DELETE). Mechanical ruff isort cleanup in bootstrap.py + signup.py. |
| Polish round 2 (#24) | **Race hardening on `grant_role` + `grant_workspace_role`.** `rbac/grants.py:grant_role` — replaced `ON CONFLICT DO NOTHING` with explicit pre-SELECT using `IS NOT DISTINCT FROM` (catches duplicates uniformly for both `workspace_id IS NULL` platform grants and NOT NULL workspace grants — closes the Postgres NULLS DISTINCT foot-gun). `services/workspace_role_grants.py:grant_workspace_role` — replaced pre-SELECT+INSERT with `INSERT ... ON CONFLICT DO NOTHING RETURNING` + fallback SELECT (closes the TOCTOU race window so concurrent identical grants both see success). |

Backend authorization is **fully resolver/permission-driven** at both platform AND workspace scope, and consistent with RLS (same `0007` fns). Frontend is permission-keys-driven for nav, shells, route gates, and every admin surface. The MeResponse keeps the enum fields additively (LATE cleanup) so the legacy `tenant_memberships.role` / `platform_users.role` enum columns can still be read by per-page code that hasn't yet migrated — but every NEW gate (P6c + P6d) uses permissions.

### NEXT

1. **First product feature (TBD by user).** The admin surface is complete. From now on, new features should use:
   - `require_permission("<feature>.<action>")` on backend routes (add the perm key to `apps/api/src/xtrusio_api/rbac/catalog.py:CATALOG` + bind to relevant system roles in `SYSTEM_ROLE_PERMISSIONS`).
   - `hasPlatformPerm()` / `hasWorkspacePerm()` from `@/lib/me-adapter` for the UI gate; `<Forbidden />` fallback per route.
   - Tenancy: `workspace_id` scoping via existing RLS + service-layer filters; new tables FK to `tenants(id) ON DELETE CASCADE`.
   - Audit: `core/audit.write_audit_event` for any mutation that should land in the audit log.
   - New pages drop under `_app.platform.<feature>.tsx` or `_app.workspace.$workspaceId.<feature>.tsx` and inherit the shell.
2. **Outstanding controller-run gate (deferred per user direction during the P6c/P6d sprint, "we can test later"):** ONE end-of-night full sweep `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check` from a clean DB to verify all four merges (#19, #20, #21, #22) together. Per-slice fast gates (typecheck + lint + focused pytest + vitest) all passed pre-merge; the slow full backend pytest sweep is the only outstanding verification.
3. **🔒 LATE cleanup** (only after every backend enum read is gone — `/me` (P3b additive), onboarding/invite-accept/bootstrap still legitimately write the enum rows; `0008` downgrade restores the enum-reading OR-form so the enum columns must exist while `0008` is reversible): drop `platform_users.role` + `tenant_memberships.role` columns + the `platform_role`/`tenant_role` enum types via a new migration.
4. **Legacy `users-page.tsx` cleanup** (P6d follow-up): the platform-invites UI in `apps/web/src/components/users-page.tsx` is no longer mounted by any route (replaced by `<PlatformUsersPage>` at `/platform/users`). Either fold platform-invite UI back into `<PlatformUsersPage>` as a tab/section, or delete the orphaned file once a replacement path for platform-invite management is decided.
5. **Smaller backlog items** (status as of 2026-05-23):
   - ~~Narrow `except Exception` blocks in invite services~~ — **DRAINED by #23**.
   - ~~`grant_role` (`rbac/grants.py`) `ON CONFLICT DO NOTHING` + Postgres NULLS DISTINCT~~ — **DRAINED by #24** (pre-SELECT pattern with `IS NOT DISTINCT FROM`).
   - ~~`DELETE /api/platform/users/{user_id}/roles/{grant_id}` consistency polish~~ — **DRAINED by #23**.
   - ~~P5 `grant_workspace_role` concurrent-duplicate-grant race~~ — **DRAINED by #24** (`INSERT ... ON CONFLICT DO NOTHING RETURNING` + fallback SELECT).
   - **`gotrue` → `supabase_auth` migration** — STILL DEFERRED, now bigger-than-polish. Attempted during the #24 session; reverted because `supabase 2.10` still imports `gotrue` internally, so a naked import-swap would NOT remove the deprecation warning (it still fires from `supabase`'s `__init__.py`). The real fix requires upgrading `supabase` to `>=2.20` which transitively requires `pydantic >= 2.10` — current pin is `~= 2.9.0`, used pervasively across schemas. **Path forward:** dedicated PR for a coordinated `supabase + pydantic` major-minor upgrade with full backend pytest re-verification. ~1-2 hr of focused work; not blocking new-feature work.

### Pre-existing `main` debt (unchanged, not from any phase)

- Managed DB `platform_settings.signups_enabled` live state → `tests/routes/test_signup.py::{test_signup_status_default_false,test_signup_disabled_returns_403}` env-flaky (pass/fail by state).
- Shared-DB mid-run pollution fragility → ALWAYS `make test-clean` before a gate run; serialized DB access.

### Still USER-DRIVEN, never agent-run

Browser/e2e smokes needing real `.env` + `make dev`/OrbStack + real inboxes.

### Operator artifacts still required

- `.env` includes `STARTUP_RECONCILE_TOLERANT=false` (required Settings field, no `Field` default).
- GitHub Actions secrets for the `xtrusio-ci` managed Supabase project: `CI_DATABASE_URL`, `CI_SUPABASE_URL`, `CI_SUPABASE_ANON_KEY`, `CI_SUPABASE_SERVICE_ROLE_KEY`, `CI_SUPABASE_JWKS_URL`. CI gates advisory until set.

### Branches on origin

All feature/polish branches deleted post-merge (cleanup done 2026-05-23). `main` is the only branch.

---

## Durable record

Specs: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` (RBAC engine), `docs/superpowers/specs/2026-05-22-rbac-p6c-admin-uis-design.md` (P6c + P6d scope split). Plans: `docs/superpowers/plans/2026-05-1{7,8,9}-rbac-*.md` (P1, P6a, P2, P3a, P3b, P3c), `docs/superpowers/plans/2026-05-20-rbac-p4-platform-admin.md`, `docs/superpowers/plans/2026-05-20-type-the-tests.md`, `docs/superpowers/plans/2026-05-21-rbac-p5-workspace-admin.md`, `docs/superpowers/plans/2026-05-21-rbac-p6b-frontend-shells.md`, `docs/superpowers/plans/2026-05-22-rbac-p6c-slice-{1,2,3}-*.md`, `docs/superpowers/plans/2026-05-23-rbac-p6d-admin-surface-completion.md`. PR bodies live alongside as `docs/superpowers/PR-rbac-*-body.md`. Persistent memory at `~/.claude/projects/-Users-jpsingh-Developer-Projects-xtrusio/memory/` is machine-local (does NOT travel) — this HANDOFF + spec + plans are the cross-machine record.
