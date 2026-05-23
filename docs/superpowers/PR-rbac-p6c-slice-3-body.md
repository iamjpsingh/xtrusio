# P6c Slice 3 — Workspace Members port + platform nav + cleanup

Closes out P6c's pure-frontend tail: the workspace owner now has an invite-only Members surface; the platform sidebar exposes the Roles + Audit log pages added in Slices 1 + 2; `UserMenu` and `tenant-users-page` consume the shared `useMe()` adapter; and the Workspace Settings placeholder no longer references an endpoint that doesn't exist yet (P6d will land that).

## Summary

- **Platform nav** — `apps/web/src/lib/nav.ts:platformNav` gains Roles (gated `platform.roles.manage`) and Audit log (gated `platform.audit.read`). Both Slice-1 and Slice-2 pages are now reachable from the sidebar.
- **`<UserMenu>` rewrite** — drops the local `type Me` and the duplicate inline `useQuery(["me"])`; consumes `useMe()` from `@/lib/me-adapter`. Badge renders from `me.platform.role` (additive enum on `MeResponse`).
- **`tenant-users-page` enum → permission** — `canInvite` switches from the legacy `myTenant.role === "owner" \|\| myTenant.role === "admin"` enum check to `hasWorkspacePerm(me, myTenant.id, "workspace.members.invite")`. Last enum-role check on this page is gone. The `InviteTenantDialog` still receives an `"owner" | "admin"` inviter-role (legacy invite-contract concern; intentionally untouched in this slice).
- **`<WorkspaceMembersPage>`** — new workspace-owner-driven invite-only port of the InviteDialog flow. Page-level gate `workspace.members.read` (renders `<Forbidden />` if missing); button-level gate `workspace.members.invite`. Includes an explicit "Member listing ships in P6d" notice so the empty state isn't mistaken for a bug. Lives at `apps/web/src/routes/_app.workspace.$workspaceId.members.tsx`, replacing the P6b placeholder.
- **Workspace Settings copy fix** — drops the misleading `/api/workspaces/$wid/settings` reference (endpoint doesn't exist yet) for `Workspace-scoped settings ship in P6d.` Route stays a placeholder.

## Architecture choices

- **Not consolidating `tenant-users-page` with `<WorkspaceMembersPage>`** — they live under different routes (`/platform/clients/$slug/users` is a platform-admin view of a tenant's invites; `/workspace/$wid/members` is a workspace-owner view of their own workspace). Different consumers, different gating; premature abstraction risk if consolidated before a real member-listing endpoint exists.
- **No `as` casts in the invite-role narrow.** The plan's snippet used `myTenant.role as "owner" | "admin"` which fails `noUncheckedIndexedAccess`. Replaced with a value-narrowing ternary that's TS-safe and semantically equivalent under the P3a invite contract.
- **`Body({ me })` typed as `MeResponse | null`** instead of `ReturnType<typeof useMe>["me"]` — matches the actual `useMe()` return signature and avoids tying component prop types to a hook's return-type internals.
- **No new shadcn primitives, no new shared blocks.** The slice consumes the building blocks from Slices 1 + 2 (`<Forbidden />`, `qk`, `me-adapter`, `error-messages`).
- **No backend changes.** Alembic head stays at `0009`.

## Test plan

- [x] `pnpm --filter @xtrusio/web typecheck` — exit 0 (clean `tsc -b --noEmit`)
- [x] `pnpm --filter @xtrusio/web exec eslint <slice files>` — clean (no errors, no warnings)
- [x] `pnpm --filter @xtrusio/web exec vitest run` — **149/149 PASS** across 34 test files
- [x] New tests:
  - `workspace-members-page.test.tsx` — 5 tests (Forbidden, ships-in-P6d notice, hidden-invite, visible-invite + list, revoke + invalidation)
  - `user-menu.test.tsx` — 3 tests (Badge from `me.platform.role`, no-Badge when `me.platform` is null, signOut)
  - `platform-sidebar.test.tsx` — 4 added (hide/show for Roles + Audit log)
  - `tenant-users-page.test.tsx` — 2 added (permission-driven button visibility)
- [ ] Full `STARTUP_RECONCILE_TOLERANT=false make check` — **deferred to a single end-of-P6c/P6d gate** per user direction.
- [ ] Manual: workspace owner sees the invite UI at `/workspace/<wid>/members`; an editor (no `workspace.members.invite`) sees the Members surface but no invite button; an outsider (no `workspace.members.read`) sees `<Forbidden />`.
- [ ] Manual: platform sidebar shows Roles + Audit log for super_admin; both items hidden for a platform-admin without `platform.roles.manage` (Roles) / `platform.audit.read` (Audit log).
- [ ] Manual: `<UserMenu>` Badge reflects `me.platform.role` text; nothing rendered when `me.platform` is null.

## What's NOT in this PR

- Member listing UI / `GET /api/workspaces/{wid}/members` endpoint — **P6d**.
- Grant-management UIs (platform + workspace) — **P6d**.
- Workspace Settings UI / endpoint — **P6d**.
- `tenant-users-page` consolidation with `<WorkspaceMembersPage>` — out of scope; see Architecture choices.

## Next

**P6d** — the three missing backend endpoints (`GET /api/platform/users`, `GET /api/workspaces/{wid}/members`, `GET/PUT /api/workspaces/{wid}/settings`) plus two new permission catalog entries (`workspace.settings.read` + `workspace.settings.manage`) plus the shared `<GrantManagerDialog>` + per-scope grant UIs + `<WorkspaceSettingsPage>`. Plan at `docs/superpowers/plans/2026-05-23-rbac-p6d-admin-surface-completion.md`. After P6d, the admin surface is complete and the first product feature can start.
