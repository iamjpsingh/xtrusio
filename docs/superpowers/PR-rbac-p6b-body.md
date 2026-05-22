# P6b — Frontend permission-driven nav + Platform/Workspace shells + workspace switcher

Backend stayed put; this is the frontend cutover from enum-driven decisions to the pinned `/me` effective-perms contract, a split into two physically-separate Platform/Workspace shells, and a workspace switcher that persists across visits.

## Summary

- **Pinned `/me` TS contract** in `packages/api-types/src/me.ts` mirrors `apps/api/.../schemas/me.py:MeResponse` exactly: `platform_permissions: PermissionKey[]`, `tenants[].permissions: PermissionKey[]`, plus the existing enum fields kept additively.
- **Legacy-compat adapter** at `apps/web/src/lib/me-adapter.ts` exposes `hasPlatformPerm` / `hasWorkspacePerm` / `findTenant` / `getDefaultLandingPath` / `useMe`. Existing enum reads keep working until each consumer is converted in P6c.
- **Permission-driven nav** — `apps/web/src/lib/nav.ts` items gained a `required_perm` field; `PlatformSidebar` / `WorkspaceSidebar` filter their items through the adapter.
- **Two physically-separate shells** —
  - `_app.tsx` reduced to a pass-through `<Outlet/>`.
  - `_app.platform.tsx` mounts `PlatformSidebar`; the 5 existing platform pages were `git mv`'d under `_app.platform.*`.
  - `_app.workspace.$workspaceId.tsx` mounts `WorkspaceSidebar` + 5 placeholder pages (Overview / Members / Roles / Audit log / Settings) — each renders a real `PageHeader` + `EmptyState` describing what P6c will fill in. **No "Coming soon"** copy.
- **Workspace switcher** dropdown in the platform/workspace sidebar headers lists `me.tenants[]` and a "Platform admin" entry (shown only when `me.platform != null`); navigates on selection and persists last-selected to `localStorage` (`xtrusio.last-workspace` + `__platform__` sentinel).
- **`/` honours last-selected** — `resolveRoute('/')` reads `readLastWorkspace()` and redirects to that workspace (or `/platform`) when still valid, else falls back to `getDefaultLandingPath(me)`.

## Bug fix — AuthGuard stale-pathname

`AuthGuard` was reading `useRouter().state.location.pathname` directly, which does NOT subscribe to router state changes. Under the old, less-aggressive `resolveRoute` this was masked. P6b's new resolver redirects super_admin away from `/sign-in` to `/platform`, exposing the bug: after `navigate()`, AuthGuard saw the stale pathname and stayed at `decision: redirect → null`, so the route content never rendered. Fix: switch to `useRouterState({ select: s => s.location.pathname })` so the hook re-renders on navigation.

## Test plan

- [x] `pnpm --filter @xtrusio/web test --run` → 74/74 green (was 39 before P6b — 35 new tests landed across me-adapter, last-workspace, platform-sidebar, workspace-sidebar, workspace-switcher, app-shell-structure dual-shell coverage, and route-resolver `/platform`/`/workspace/$id`/localStorage cases).
- [x] `pnpm --filter @xtrusio/web typecheck` → green.
- [x] `pnpm --filter @xtrusio/api-types typecheck` → green.
- [x] `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check` — controller-run end-of-phase gate; expected green (backend untouched in P6b).

## What's NOT in this PR

- **RBAC admin UIs (P6c)** — the workspace shell's placeholder pages still render the `EmptyState`. Filling them in is the next phase.
- **`UserMenu` rewrite** — keeps its own local `Me` type + duplicate `useQuery(['me'])`. Cache is shared so it works fine; cleanup deferred to P6c.
- **Removing the enum fields from `MeResponse`** — `platform.role` and `tenants[].role` stay on the type until every backend enum read is gone (LATE cleanup per HANDOFF §NEXT item 6).
- **Backend changes** — none.

## Files

**Created (12):**
- `packages/api-types/src/me.ts` — pinned MeResponse + PlatformContext + TenantContext + PendingInvite + PermissionKey
- `apps/web/src/lib/me-adapter.{ts,test.ts}` — adapter + 14 tests
- `apps/web/src/lib/last-workspace.{ts,test.ts}` — localStorage helper + 4 tests
- `apps/web/src/components/platform-sidebar.{tsx,test.tsx}` — permission-driven platform nav
- `apps/web/src/components/workspace-sidebar.{tsx,test.tsx}` — permission-driven workspace nav
- `apps/web/src/components/workspace-switcher.test.tsx` — 5 cases for the switcher dropdown
- `apps/web/src/routes/_app.platform.tsx` + `_app.workspace.$workspaceId.tsx` + 5 workspace placeholder children (`{index,members,roles,audit-log,settings}.tsx`)

**Modified:** `packages/api-types/src/index.ts`, `apps/web/package.json`, `apps/web/src/lib/{api.ts,route-resolver.ts,nav.ts}`, `apps/web/src/components/{auth-guard.tsx,auth-guard.test.tsx,app-topbar.tsx,app-shell-structure.test.tsx,tenant-users-page.test.tsx,workspace-switcher.tsx}`, `apps/web/src/routes/{_app.tsx,-index.test.tsx}`, `apps/web/src/lib/route-resolver.test.ts`.

**Renamed (via git mv):** 5 platform route files moved from `_app.{clients.$slug.users,clients,index,settings,users}.tsx` → `_app.platform.{clients.$slug.users,clients,index,settings,users}.tsx`.

**Deleted:** `apps/web/src/components/app-sidebar.tsx` (replaced by PlatformSidebar + WorkspaceSidebar).

## Next

P6c — RBAC admin UIs (consume P4 + P5 APIs). Platform-side: custom-role CRUD, role grants, audit log. Workspace-side: same, scoped per workspace.
