# RBAC P6b — Frontend Permission-Driven Nav + Platform/Workspace Shells + Workspace Switcher

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin the `/me` effective-perms TS contract in `@xtrusio/api-types`, add a legacy-compat adapter that exposes `hasPlatformPerm`/`hasWorkspacePerm`, split the single in-app shell into two physically-separate shells (`/platform/*` + `/workspace/$workspaceId/*`), make sidebar nav permission-driven, and add a workspace switcher in the topbar with localStorage persistence.

**Architecture:** Backend `/me` (P3b) already returns `platform_permissions: string[]` and `tenants[].permissions: string[]` ADDITIVELY alongside the legacy enum `platform.role` / `tenants[].role`. P6b is a frontend-only re-organisation: (1) lift the `MeResponse` type from `apps/web/src/lib/route-resolver.ts` into `packages/api-types/src/me.ts` and add the additive permission arrays so the shape is enforced at compile time; (2) build a tiny `me-adapter.ts` with `hasPlatformPerm(key)`, `hasWorkspacePerm(workspaceId, key)`, and helpers for the current workspace / last-selected scope so consumers migrate page-by-page; (3) split `_app.tsx` (currently the sole sidebar host) so the platform-side routes live under a new `_app.platform.*` layout (PlatformSidebar) and tenant-side routes live under a new `_app.workspace.$workspaceId.*` layout (WorkspaceSidebar with workspace-scoped nav: Members / Roles / Audit Log / Settings, gated by `workspace.*` perms); (4) drop a workspace switcher into the topbar that lists `me.tenants[]` + a "Platform admin" entry (only when `me.platform != null`) and persists last-selected to `localStorage` so users land back where they were. The adapter keeps enum reads working until every consumer is converted in a later phase.

**Tech Stack:** TypeScript (strict, ES2022, `verbatimModuleSyntax`, `noUncheckedIndexedAccess`), React 19, TanStack Router (file-based, `$param` syntax), TanStack Query v5, Vitest 2, React Testing Library 16, Tailwind 4, shadcn/radix UI primitives, Vite 8. Workspace package: pnpm + Turbo. New cross-package import: `@xtrusio/api-types`.

---

## File Structure

Files are listed in the order the slices touch them. Every Modify item names the exact line range that gets rewritten so the implementer is not hunting.

### Create

| Path | Purpose |
|---|---|
| `packages/api-types/src/me.ts` | Pinned `/me` TS contract (mirrors `apps/api/src/xtrusio_api/schemas/me.py`). Owns `MeResponse`, `PlatformContext`, `TenantContext`, `PendingInvite`, and the `PermissionKey` type. |
| `packages/api-types/src/me.test.ts` | Compile-time fixture asserting the type accepts a sample backend payload and rejects a missing `platform_permissions` field. |
| `apps/web/src/lib/me-adapter.ts` | `hasPlatformPerm` / `hasWorkspacePerm` / `findTenant` / `getDefaultLandingPath` / `LAST_WORKSPACE_KEY` plus the React hook `useMe()` that wraps the shared `["me"]` `useQuery`. |
| `apps/web/src/lib/me-adapter.test.ts` | Unit tests for `hasPlatformPerm` true/false, `hasWorkspacePerm` (matches by `workspaceId`, returns false for unknown id), `getDefaultLandingPath` (platform > first tenant > onboarding). |
| `apps/web/src/lib/last-workspace.ts` | Tiny localStorage wrapper (`readLastWorkspace`, `writeLastWorkspace`, `clearLastWorkspace`) — pure functions, easy to unit-test, no side effects at import time. |
| `apps/web/src/lib/last-workspace.test.ts` | Vitest spec exercising read/write/clear against a jsdom `localStorage`. |
| `apps/web/src/components/platform-sidebar.tsx` | Platform shell sidebar: reads `platformNav`, filters items via `hasPlatformPerm`, renders Xtrusio brand + `WorkspaceSwitcher`. |
| `apps/web/src/components/workspace-sidebar.tsx` | Workspace shell sidebar: reads `workspaceNav`, filters items via `hasWorkspacePerm(currentWorkspaceId, ...)`, shows workspace name in header + `WorkspaceSwitcher`. |
| `apps/web/src/components/workspace-switcher.tsx` | Dropdown listing `me.tenants[]` + "Platform admin" (when `me.platform != null`); selecting an item writes to `last-workspace.ts` and navigates to the right URL. |
| `apps/web/src/components/workspace-switcher.test.tsx` | Vitest spec covering: lists every tenant; shows "Platform admin" only when platform present; selecting a tenant calls `navigate({ to: "/workspace/$workspaceId", params })`; persists to localStorage. |
| `apps/web/src/components/platform-sidebar.test.tsx` | Filters nav items by `hasPlatformPerm`. Renders Settings only when `platform.settings.read` is present; hides it otherwise. |
| `apps/web/src/components/workspace-sidebar.test.tsx` | Filters nav items by `hasWorkspacePerm(workspaceId, ...)`. Renders Audit Log only when `workspace.audit.read` is present. |
| `apps/web/src/routes/_app.platform.tsx` | Platform shell layout route (`SidebarProvider` + `PlatformSidebar` + `AppTopbar`). |
| `apps/web/src/routes/_app.platform.index.tsx` | Platform dashboard (moved from `_app.index.tsx`). |
| `apps/web/src/routes/_app.platform.users.tsx` | Platform Users page (moved from `_app.users.tsx`). |
| `apps/web/src/routes/_app.platform.clients.tsx` | Platform Clients list (moved from `_app.clients.tsx`). |
| `apps/web/src/routes/_app.platform.clients.$slug.users.tsx` | Tenant users sub-route (moved from `_app.clients.$slug.users.tsx`). Stays under `/platform/clients/$slug/users` because this is a platform-admin view of a tenant; the workspace-scoped Members page is a different surface (`/workspace/$workspaceId/members`). |
| `apps/web/src/routes/_app.platform.settings.tsx` | Platform Settings (moved from `_app.settings.tsx`). |
| `apps/web/src/routes/_app.workspace.$workspaceId.tsx` | Workspace shell layout route (resolves `params.workspaceId` against `me.tenants[]`, redirects to `/` if unknown). |
| `apps/web/src/routes/_app.workspace.$workspaceId.index.tsx` | Workspace overview (placeholder page that still renders inside the WorkspaceSidebar shell — body is "Coming soon" copy + page header; page bodies for Members/Roles/Audit Log/Settings ship in P6c). |
| `apps/web/src/routes/_app.workspace.$workspaceId.members.tsx` | Workspace Members placeholder (P6c implements the body). |
| `apps/web/src/routes/_app.workspace.$workspaceId.roles.tsx` | Workspace Roles placeholder (P6c implements the body). |
| `apps/web/src/routes/_app.workspace.$workspaceId.audit-log.tsx` | Workspace Audit Log placeholder (P6c implements the body). |
| `apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx` | Workspace Settings placeholder (P6c implements the body). |

### Modify

| Path | Lines | Change |
|---|---|---|
| `packages/api-types/src/index.ts` | 1-3 | Replace placeholder with `export * from "./me";`. |
| `apps/web/package.json` | 14-31 (dependencies) | Add `"@xtrusio/api-types": "workspace:*"` to dependencies. |
| `apps/web/src/lib/api.ts` | 1-2, 54-56 | Re-import `MeResponse` from `@xtrusio/api-types` instead of `./route-resolver`. Body unchanged. |
| `apps/web/src/lib/route-resolver.ts` | 1-41 (full) | (a) Drop the local `MeResponse` declaration in favour of `import type { MeResponse } from "@xtrusio/api-types";`. (b) Rewrite `resolveRoute` to know about `/platform/*` and `/workspace/$workspaceId/*` prefixes: any unauth → `/sign-in`; pending invite → `/accept-invite`; unprovisioned → `/onboarding`; otherwise pick default landing from `getDefaultLandingPath(me)` (platform first, then first tenant). `PLATFORM_ONLY` is replaced with prefix logic (`/platform/*` requires `me.platform != null`; `/workspace/$wid/*` requires `wid ∈ me.tenants`). |
| `apps/web/src/lib/route-resolver.test.ts` | 1-62 (full) | Update fixtures to the new `MeResponse` (include `platform_permissions: []`, `tenants[].permissions: []`). Add cases for `/platform/*` and `/workspace/$wid/*` redirects + default landing. |
| `apps/web/src/lib/nav.ts` | 1-14 (full) | Add `required_perm: string` on `NavItem`. Tag each `platformNav` entry with its catalog key. Add `workspaceNav: NavItem[]` (Overview / Members / Roles / Audit Log / Settings) with the corresponding `workspace.*` perm keys. Add `Dashboard` for the workspace overview using a placeholder perm that every member has (`workspace.members.read`). |
| `apps/web/src/components/auth-guard.test.tsx` | 23-31, 52-74 | Update fixtures to additive shape (`platform_permissions: ["..."]`, `tenants[].permissions`). |
| `apps/web/src/components/app-shell-structure.test.tsx` | 22-31, 55-67 | Add `platform_permissions: ["platform.users.read", ...]` to the mocked `fetchMe`. Adjust the existing assertion to load `/platform` instead of `/`. Add a new test asserting `/workspace/<id>` renders the workspace sidebar variant. |
| `apps/web/src/routes/_app.tsx` | 1-23 | Strip the SidebarProvider/AppSidebar — leave only `<Outlet />` (the two child layouts own their own shells). The file remains as a pathless layout route so route-tree generation still works. |
| `apps/web/src/components/app-topbar.tsx` | 1-56 | Replace the `findLabel` use of `platformNav` with a label that's "Platform" or the current workspace name based on URL. Mount `<WorkspaceSwitcher />` to the left of the breadcrumb. |

### Delete

| Path | Reason |
|---|---|
| `apps/web/src/components/app-sidebar.tsx` | Replaced by `platform-sidebar.tsx` + `workspace-sidebar.tsx`. The single-sidebar abstraction does not fit two shells. |
| `apps/web/src/routes/_app.index.tsx` | Moved to `_app.platform.index.tsx`. |
| `apps/web/src/routes/_app.users.tsx` | Moved to `_app.platform.users.tsx`. |
| `apps/web/src/routes/_app.clients.tsx` | Moved to `_app.platform.clients.tsx`. |
| `apps/web/src/routes/_app.clients.$slug.users.tsx` | Moved to `_app.platform.clients.$slug.users.tsx`. |
| `apps/web/src/routes/_app.settings.tsx` | Moved to `_app.platform.settings.tsx`. |

> The autogenerated `apps/web/src/routeTree.gen.ts` will rewrite itself the next time the Vite dev server / build runs. Do not hand-edit it. Re-run `pnpm --filter @xtrusio/web build` once after the route file moves so the generated tree is in the commit that lands the moves.

> TanStack file-route naming reminder (verified against the existing tree): dot segments map to URL segments, `$param` segments are dynamic, the `_app` prefix is a pathless layout route. So `_app.workspace.$workspaceId.members.tsx` mounts at `/workspace/$workspaceId/members` and inherits the layout from `_app.workspace.$workspaceId.tsx`.

---

## Slice A — Pinned `/me` TS Contract + Adapter

**Goal:** Move `MeResponse` into `@xtrusio/api-types`, add the additive permission arrays, add `apps/web` dependency on the package, and ship `me-adapter.ts` with the public API the rest of the plan depends on.

### Task A1: Create the pinned `/me` types in `@xtrusio/api-types`

**Files:**
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/packages/api-types/src/me.ts`
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/packages/api-types/src/index.ts` (lines 1-3, full file)

- [ ] **Step 1: Write the type file**

```ts
// packages/api-types/src/me.ts
// Mirror of apps/api/src/xtrusio_api/schemas/me.py:MeResponse. The enum
// fields (`platform.role`, `tenants[].role`) are kept ADDITIVELY alongside
// the resolver-derived permission arrays so frontend consumers can migrate
// component-by-component. The enum fields will be removed in a later phase
// once every consumer reads permissions instead.

export type PlatformRole = "super_admin" | "admin" | "editor";
export type TenantRole = "owner" | "admin" | "editor" | "read_only";

/** Permission key as defined in apps/api/src/xtrusio_api/rbac/catalog.py. */
export type PermissionKey = string;

export type PlatformContext = {
  role: PlatformRole;
  is_active: boolean;
};

export type TenantContext = {
  id: string;
  slug: string;
  name: string;
  role: TenantRole;
  /** Resolver-derived effective workspace permission keys. */
  permissions: PermissionKey[];
};

export type PendingInvite = {
  kind: "platform" | "tenant";
  id: string;
  tenant_id: string | null;
  role: string;
};

export type MeResponse = {
  user_id: string;
  email: string;
  platform: PlatformContext | null;
  /** Resolver-derived effective platform permission keys (empty if none). */
  platform_permissions: PermissionKey[];
  tenants: TenantContext[];
  pending_invite: PendingInvite | null;
};
```

- [ ] **Step 2: Re-export from the package index**

Replace the entire contents of `/Users/jpsingh/Developer/Projects/xtrusio/packages/api-types/src/index.ts` with:

```ts
export * from "./me";
```

- [ ] **Step 3: Verify the package typechecks**

Run: `pnpm --filter @xtrusio/api-types typecheck`
Expected: exits 0 with no output (or just the tsc banner).

- [ ] **Step 4: Commit**

```bash
git add packages/api-types/src/me.ts packages/api-types/src/index.ts
git commit -m "feat(api-types): pin /me response shape with additive permission arrays"
```

### Task A2: Add `@xtrusio/api-types` as a dependency of `@xtrusio/web`

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/package.json` (dependencies block, lines 14-31)

- [ ] **Step 1: Add the workspace dependency**

In `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/package.json`, add this line inside the `"dependencies"` object (alphabetical order — put it right after `"@tanstack/react-router"`):

```json
    "@xtrusio/api-types": "workspace:*",
```

- [ ] **Step 2: Re-install so pnpm wires the workspace symlink**

Run: `pnpm install`
Expected: "Already up to date" or a single line about creating `apps/web/node_modules/@xtrusio/api-types`.

- [ ] **Step 3: Confirm the import path resolves**

Run: `pnpm --filter @xtrusio/web exec node -e "console.log(require.resolve('@xtrusio/api-types/src/me.ts', { paths: ['./'] }))"` (this exact line is illustrative — the real proof is the typecheck in the next task). Skip if it errors; the typecheck in Task A3 is the load-bearing gate.

- [ ] **Step 4: Commit**

```bash
git add apps/web/package.json pnpm-lock.yaml
git commit -m "chore(web): depend on @xtrusio/api-types (workspace)"
```

### Task A3: Switch `apps/web` to import `MeResponse` from `@xtrusio/api-types`

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/api.ts` (line 2)
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/route-resolver.ts` (lines 1-9)

- [ ] **Step 1: Update `api.ts` to import from the package**

Replace line 2 of `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/api.ts`:

```ts
import type { MeResponse } from "@xtrusio/api-types";
```

- [ ] **Step 2: Replace the local `MeResponse` declaration in `route-resolver.ts`**

Replace lines 1-9 of `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/route-resolver.ts` with:

```ts
import type { MeResponse } from "@xtrusio/api-types";

export type { MeResponse };
export type AuthState = { session: string | null; me: MeResponse | null };
export type RouteDecision = { kind: "render" } | { kind: "redirect"; to: string };
```

Leave the rest of the file untouched for now — Slice B rewrites `resolveRoute` itself.

- [ ] **Step 3: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: compiles cleanly. The `MeResponse` reference in `api.ts` resolves through the package; `route-resolver.ts` re-exports the type for callers that still import from there.

- [ ] **Step 4: Run the existing test suite to confirm nothing regressed**

Run: `pnpm --filter @xtrusio/web test`
Expected: all existing tests still pass (route-resolver.test.ts, auth-guard.test.tsx, etc.).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/api.ts apps/web/src/lib/route-resolver.ts
git commit -m "refactor(web): import MeResponse from @xtrusio/api-types"
```

### Task A4: Write the `me-adapter.ts` unit tests (FAILING)

**Files:**
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/me-adapter.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// apps/web/src/lib/me-adapter.test.ts
import { describe, expect, it } from "vitest";
import type { MeResponse } from "@xtrusio/api-types";
import {
  hasPlatformPerm,
  hasWorkspacePerm,
  findTenant,
  getDefaultLandingPath,
} from "./me-adapter";

const empty: MeResponse = {
  user_id: "u",
  email: "x@x.com",
  platform: null,
  platform_permissions: [],
  tenants: [],
  pending_invite: null,
};

const platformAdmin: MeResponse = {
  ...empty,
  platform: { role: "admin", is_active: true },
  platform_permissions: ["platform.users.read", "platform.clients.read"],
};

const tenantOwner: MeResponse = {
  ...empty,
  tenants: [
    {
      id: "t1",
      slug: "acme",
      name: "Acme",
      role: "owner",
      permissions: ["workspace.members.read", "workspace.members.invite"],
    },
  ],
};

describe("hasPlatformPerm", () => {
  it("returns false when `me` is null", () => {
    expect(hasPlatformPerm(null, "platform.users.read")).toBe(false);
  });

  it("returns false when the key is not granted", () => {
    expect(hasPlatformPerm(platformAdmin, "platform.settings.manage")).toBe(false);
  });

  it("returns true when the key is granted", () => {
    expect(hasPlatformPerm(platformAdmin, "platform.users.read")).toBe(true);
  });
});

describe("hasWorkspacePerm", () => {
  it("returns false when `me` is null", () => {
    expect(hasWorkspacePerm(null, "t1", "workspace.members.read")).toBe(false);
  });

  it("returns false for an unknown workspace id", () => {
    expect(hasWorkspacePerm(tenantOwner, "missing", "workspace.members.read")).toBe(false);
  });

  it("returns true when the workspace grants the key", () => {
    expect(hasWorkspacePerm(tenantOwner, "t1", "workspace.members.invite")).toBe(true);
  });

  it("returns false when the workspace exists but does not grant the key", () => {
    expect(hasWorkspacePerm(tenantOwner, "t1", "workspace.audit.read")).toBe(false);
  });
});

describe("findTenant", () => {
  it("returns the tenant by id", () => {
    expect(findTenant(tenantOwner, "t1")?.slug).toBe("acme");
  });

  it("returns undefined for an unknown id", () => {
    expect(findTenant(tenantOwner, "nope")).toBeUndefined();
  });

  it("returns undefined when `me` is null", () => {
    expect(findTenant(null, "t1")).toBeUndefined();
  });
});

describe("getDefaultLandingPath", () => {
  it("sends platform users to /platform", () => {
    expect(getDefaultLandingPath(platformAdmin)).toBe("/platform");
  });

  it("sends tenant-only users to their first workspace", () => {
    expect(getDefaultLandingPath(tenantOwner)).toBe("/workspace/t1");
  });

  it("sends unprovisioned users to /onboarding", () => {
    expect(getDefaultLandingPath(empty)).toBe("/onboarding");
  });

  it("returns /sign-in when `me` is null", () => {
    expect(getDefaultLandingPath(null)).toBe("/sign-in");
  });
});
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pnpm --filter @xtrusio/web test --run src/lib/me-adapter.test.ts`
Expected: FAIL with "Cannot find module './me-adapter'" or "hasPlatformPerm is not a function".

### Task A5: Implement `me-adapter.ts`

**Files:**
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/me-adapter.ts`

- [ ] **Step 1: Write the implementation**

```ts
// apps/web/src/lib/me-adapter.ts
// Legacy-compat adapter over the pinned MeResponse shape from
// @xtrusio/api-types. Exposes permission-key checks so call sites migrate off
// `me.platform.role === "super_admin"` style enum reads. Enum fields stay
// available on MeResponse until every consumer is converted (later phase).

import { useQuery } from "@tanstack/react-query";
import type { MeResponse, PermissionKey, TenantContext } from "@xtrusio/api-types";
import { fetchMe } from "./api";

export function hasPlatformPerm(me: MeResponse | null, key: PermissionKey): boolean {
  if (!me) return false;
  return me.platform_permissions.includes(key);
}

export function hasWorkspacePerm(
  me: MeResponse | null,
  workspaceId: string,
  key: PermissionKey,
): boolean {
  if (!me) return false;
  const t = me.tenants.find((x) => x.id === workspaceId);
  if (!t) return false;
  return t.permissions.includes(key);
}

export function findTenant(me: MeResponse | null, workspaceId: string): TenantContext | undefined {
  if (!me) return undefined;
  return me.tenants.find((t) => t.id === workspaceId);
}

/**
 * Pick the URL the user should land on when there's no last-selected scope.
 * Order: pending invite > onboarding > platform shell > first workspace.
 */
export function getDefaultLandingPath(me: MeResponse | null): string {
  if (!me) return "/sign-in";
  if (me.pending_invite) return "/accept-invite";
  if (me.platform) return "/platform";
  const first = me.tenants[0];
  if (first) return `/workspace/${first.id}`;
  return "/onboarding";
}

/** Shared `useQuery(['me'])` hook so every consumer reuses the same cache entry. */
export function useMe(): { me: MeResponse | null; isLoading: boolean } {
  const { data, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    refetchOnWindowFocus: false,
  });
  return { me: data ?? null, isLoading };
}
```

- [ ] **Step 2: Run the tests to confirm they pass**

Run: `pnpm --filter @xtrusio/web test --run src/lib/me-adapter.test.ts`
Expected: PASS — all 13 cases green.

- [ ] **Step 3: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/me-adapter.ts apps/web/src/lib/me-adapter.test.ts
git commit -m "feat(web): add me-adapter (hasPlatformPerm/hasWorkspacePerm/useMe)"
```

### Task A6: `last-workspace.ts` localStorage helper

**Files:**
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/last-workspace.ts`
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/last-workspace.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// apps/web/src/lib/last-workspace.test.ts
import { beforeEach, describe, expect, it } from "vitest";
import { readLastWorkspace, writeLastWorkspace, clearLastWorkspace } from "./last-workspace";

describe("last-workspace", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("reads null when no value is stored", () => {
    expect(readLastWorkspace()).toBeNull();
  });

  it("round-trips a workspace id", () => {
    writeLastWorkspace("t-123");
    expect(readLastWorkspace()).toBe("t-123");
  });

  it("round-trips the sentinel for the platform shell", () => {
    writeLastWorkspace("__platform__");
    expect(readLastWorkspace()).toBe("__platform__");
  });

  it("clears the stored value", () => {
    writeLastWorkspace("t-1");
    clearLastWorkspace();
    expect(readLastWorkspace()).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pnpm --filter @xtrusio/web test --run src/lib/last-workspace.test.ts`
Expected: FAIL with "Cannot find module './last-workspace'".

- [ ] **Step 3: Implement**

```ts
// apps/web/src/lib/last-workspace.ts
// Persists the user's last-selected scope (platform sentinel or a workspace
// id) so revisits land in the right shell. Pure functions; no side effects
// at import time.

const KEY = "xtrusio.last-workspace";

/** Sentinel stored when the user's last selection was the platform shell. */
export const PLATFORM_SENTINEL = "__platform__";

export function readLastWorkspace(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function writeLastWorkspace(value: string): void {
  try {
    window.localStorage.setItem(KEY, value);
  } catch {
    /* localStorage may be disabled (Safari private mode etc.) — fail closed */
  }
}

export function clearLastWorkspace(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* see above */
  }
}
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pnpm --filter @xtrusio/web test --run src/lib/last-workspace.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/last-workspace.ts apps/web/src/lib/last-workspace.test.ts
git commit -m "feat(web): persist last-selected workspace to localStorage"
```

---

## Slice B — Route Resolver Upgrade + AuthGuard Glue

**Goal:** Teach `resolveRoute` about the new `/platform/*` and `/workspace/$workspaceId/*` prefixes; route the default landing through `getDefaultLandingPath`; keep `/onboarding`, `/accept-invite`, `/sign-in`, `/sign-up` as no-shell paths.

### Task B1: Rewrite `route-resolver.test.ts` for the new prefixes (FAILING)

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/route-resolver.test.ts` (entire file, lines 1-62)

- [ ] **Step 1: Replace the test file**

```ts
// apps/web/src/lib/route-resolver.test.ts
import { describe, expect, it } from "vitest";
import type { MeResponse } from "@xtrusio/api-types";
import { resolveRoute } from "./route-resolver";

const unprov: MeResponse = {
  user_id: "u",
  email: "x@x.com",
  platform: null,
  platform_permissions: [],
  tenants: [],
  pending_invite: null,
};
const sa: MeResponse = {
  ...unprov,
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.users.read", "platform.settings.manage"],
};
const tenant: MeResponse = {
  ...unprov,
  tenants: [
    {
      id: "t1",
      slug: "acme",
      name: "Acme",
      role: "owner",
      permissions: ["workspace.members.read"],
    },
  ],
};
const pending: MeResponse = {
  ...unprov,
  pending_invite: { kind: "tenant", id: "i", tenant_id: "t", role: "admin" },
};

describe("resolveRoute", () => {
  it("redirects unauth to /sign-in", () => {
    expect(resolveRoute({ session: null, me: null }, "/")).toEqual({
      kind: "redirect",
      to: "/sign-in",
    });
  });

  it("allows /sign-up when unauth", () => {
    expect(resolveRoute({ session: null, me: null }, "/sign-up")).toEqual({ kind: "render" });
  });

  it("pending invite forces /accept-invite", () => {
    expect(resolveRoute({ session: "s", me: pending }, "/platform")).toEqual({
      kind: "redirect",
      to: "/accept-invite",
    });
  });

  it("super_admin lands on /platform from /", () => {
    expect(resolveRoute({ session: "s", me: sa }, "/")).toEqual({
      kind: "redirect",
      to: "/platform",
    });
  });

  it("super_admin can navigate /platform/settings", () => {
    expect(resolveRoute({ session: "s", me: sa }, "/platform/settings")).toEqual({
      kind: "render",
    });
  });

  it("tenant member redirected away from /platform/*", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/platform/settings")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("tenant member can navigate to their own /workspace/$id", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/workspace/t1")).toEqual({
      kind: "render",
    });
  });

  it("tenant member can navigate to a nested /workspace/$id/members", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/workspace/t1/members")).toEqual({
      kind: "render",
    });
  });

  it("tenant member redirected away from a workspace they don't belong to", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/workspace/other")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("tenant member lands on their first workspace from /", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("unprovisioned forced to /onboarding from /platform", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/platform")).toEqual({
      kind: "redirect",
      to: "/onboarding",
    });
  });

  it("unprovisioned on /onboarding renders", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/onboarding")).toEqual({
      kind: "render",
    });
  });
});
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pnpm --filter @xtrusio/web test --run src/lib/route-resolver.test.ts`
Expected: FAIL — old `resolveRoute` doesn't know about `/platform/*` or `/workspace/$id/*` prefixes.

### Task B2: Rewrite `route-resolver.ts`

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/route-resolver.ts` (entire file)

- [ ] **Step 1: Replace the file**

```ts
// apps/web/src/lib/route-resolver.ts
import type { MeResponse } from "@xtrusio/api-types";
import { getDefaultLandingPath } from "./me-adapter";

export type { MeResponse };
export type AuthState = { session: string | null; me: MeResponse | null };
export type RouteDecision = { kind: "render" } | { kind: "redirect"; to: string };

const PUBLIC = new Set(["/sign-in", "/sign-up"]);
const UNGATED_AUTHED = new Set(["/onboarding", "/accept-invite"]);

function isPlatformPath(path: string): boolean {
  return path === "/platform" || path.startsWith("/platform/");
}

function workspaceIdFromPath(path: string): string | null {
  // Matches /workspace/<id> and /workspace/<id>/...
  const m = /^\/workspace\/([^/]+)(?:\/.*)?$/.exec(path);
  return m ? (m[1] ?? null) : null;
}

export function resolveRoute(state: AuthState, path: string): RouteDecision {
  if (!state.session) {
    return PUBLIC.has(path) ? { kind: "render" } : { kind: "redirect", to: "/sign-in" };
  }
  if (!state.me) return { kind: "render" }; // spinner rendered by caller while /me loads

  const me = state.me;

  // Pending invite takes precedence over every authed path.
  if (me.pending_invite) {
    return path === "/accept-invite"
      ? { kind: "render" }
      : { kind: "redirect", to: "/accept-invite" };
  }

  // Ungated authed pages (onboarding, accept-invite when no pending invite).
  if (UNGATED_AUTHED.has(path)) {
    if (path === "/onboarding" && (me.platform || me.tenants.length > 0)) {
      return { kind: "redirect", to: getDefaultLandingPath(me) };
    }
    return { kind: "render" };
  }

  // Platform shell — only when user has a platform context.
  if (isPlatformPath(path)) {
    return me.platform
      ? { kind: "render" }
      : { kind: "redirect", to: getDefaultLandingPath(me) };
  }

  // Workspace shell — only when the workspace id matches one of the user's tenants.
  const wid = workspaceIdFromPath(path);
  if (wid !== null) {
    const belongs = me.tenants.some((t) => t.id === wid);
    return belongs
      ? { kind: "render" }
      : { kind: "redirect", to: getDefaultLandingPath(me) };
  }

  // Anything else (notably "/") → default landing.
  return { kind: "redirect", to: getDefaultLandingPath(me) };
}
```

- [ ] **Step 2: Run the tests to confirm they pass**

Run: `pnpm --filter @xtrusio/web test --run src/lib/route-resolver.test.ts`
Expected: PASS — all 12 cases green.

- [ ] **Step 3: Update the AuthGuard test fixtures to the additive shape**

Edit `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/auth-guard.test.tsx`. Replace the two `vi.mocked(fetchMe).mockResolvedValue({...})` blocks (lines 52-58 and lines 64-70) with the additive fields.

The first block (around line 52):

```ts
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u",
      email: "x@x.com",
      platform: { role: "super_admin", is_active: true },
      platform_permissions: ["platform.users.read"],
      tenants: [],
      pending_invite: null,
    });
```

The second block (around line 64):

```ts
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u",
      email: "x@x.com",
      platform: null,
      platform_permissions: [],
      tenants: [],
      pending_invite: null,
    });
```

Also update the first test's expectation: with the new resolver, a super_admin on `/` redirects to `/platform`, so this test must move from `/` to `/platform`. Edit the `useRouter` mock at lines 7-10 to expose the path used per test, OR add a second `vi.mocked` of `useRouter` inside the test. Simplest: change the existing `pathname: "/"` mock to `pathname: "/platform"` and update the assertion to expect render (no redirect).

Replace lines 7-10 with:

```ts
let mockPathname = "/";
vi.mock("@tanstack/react-router", () => ({
  useRouter: () => ({ state: { location: { pathname: mockPathname } } }),
  useNavigate: () => navigateMock,
}));
```

Then in the first test (`renders children when user is super_admin on /`):

- Rename to: `renders children when user is super_admin on /platform`
- Set `mockPathname = "/platform";` at the start of the test, before `renderGuard()`.

In the second test (`redirects unprovisioned user to /onboarding`):

- Set `mockPathname = "/platform";` at the start of the test, before `renderGuard()`.
- Keep the assertion as-is — an unprovisioned user landing on `/platform` redirects to `/onboarding`.

- [ ] **Step 4: Run the AuthGuard tests**

Run: `pnpm --filter @xtrusio/web test --run src/components/auth-guard.test.tsx`
Expected: PASS — all 3 cases green (including the existing `inherits staleTime` smoke test).

- [ ] **Step 5: Typecheck the whole app**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/route-resolver.ts apps/web/src/lib/route-resolver.test.ts apps/web/src/components/auth-guard.test.tsx
git commit -m "feat(web): route resolver knows /platform/* and /workspace/\$id/*"
```

---

## Slice C — Two Physically-Separate Shells

**Goal:** Replace the single `_app.tsx` shell with two child layouts (`_app.platform.tsx`, `_app.workspace.$workspaceId.tsx`), move existing route files under `_app.platform.*`, and scaffold the workspace placeholder pages. Update `app-shell-structure.test.tsx` to cover both shells.

### Task C1: Reduce `_app.tsx` to a pass-through

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/routes/_app.tsx` (entire file, lines 1-23)

- [ ] **Step 1: Replace the file**

```tsx
// apps/web/src/routes/_app.tsx
// Pathless layout for every authed page. The two physically-separate shells
// live in `_app.platform.tsx` and `_app.workspace.$workspaceId.tsx`. This
// file intentionally renders only an Outlet so each shell owns its own
// SidebarProvider tree.
import { Outlet, createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app")({
  component: AppPassthrough,
});

function AppPassthrough() {
  return <Outlet />;
}
```

- [ ] **Step 2: Move the existing platform routes (file renames)**

```bash
git mv apps/web/src/routes/_app.index.tsx apps/web/src/routes/_app.platform.index.tsx
git mv apps/web/src/routes/_app.users.tsx apps/web/src/routes/_app.platform.users.tsx
git mv apps/web/src/routes/_app.clients.tsx apps/web/src/routes/_app.platform.clients.tsx
git mv apps/web/src/routes/_app.clients.\$slug.users.tsx apps/web/src/routes/_app.platform.clients.\$slug.users.tsx
git mv apps/web/src/routes/_app.settings.tsx apps/web/src/routes/_app.platform.settings.tsx
```

> Pre-flight check: `ls apps/web/src/routes/` should now show no `_app.index.tsx`, `_app.users.tsx`, `_app.clients.tsx`, `_app.clients.$slug.users.tsx`, or `_app.settings.tsx`.

- [ ] **Step 3: Update the route IDs in each renamed file**

The `createFileRoute("...")` string MUST match the new file path. Open each moved file and update the id:

- `_app.platform.index.tsx`: `createFileRoute("/_app/")` → `createFileRoute("/_app/platform/")`
- `_app.platform.users.tsx`: `createFileRoute("/_app/users")` → `createFileRoute("/_app/platform/users")`
- `_app.platform.clients.tsx`: `createFileRoute("/_app/clients")` → `createFileRoute("/_app/platform/clients")`
- `_app.platform.clients.$slug.users.tsx`: `createFileRoute("/_app/clients/$slug/users")` → `createFileRoute("/_app/platform/clients/$slug/users")`
- `_app.platform.settings.tsx`: `createFileRoute("/_app/settings")` → `createFileRoute("/_app/platform/settings")`

- [ ] **Step 4: Delete the now-unused `app-sidebar.tsx`** (it will be replaced by two new sidebars in Task C3 / C4)

```bash
git rm apps/web/src/components/app-sidebar.tsx
```

- [ ] **Step 5: Commit the move (route tree will regenerate on the next dev/build)**

```bash
git add apps/web/src/routes/_app.tsx
git commit -m "refactor(web): move platform routes under _app.platform.* (no shell yet)"
```

### Task C2: Build `PlatformSidebar` (TDD)

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/nav.ts` (entire file)
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/platform-sidebar.tsx`
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/platform-sidebar.test.tsx`

- [ ] **Step 1: Extend `nav.ts` with `required_perm` + `workspaceNav`**

Replace the entire contents of `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/nav.ts` with:

```ts
import {
  LayoutDashboard,
  Users,
  Building2,
  Settings,
  Shield,
  ScrollText,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Permission catalog key required to see this item. */
  required_perm: string;
};

/**
 * Platform-shell nav. `to` paths are relative-to-app — the Link component
 * navigates via TanStack Router so use the absolute path.
 */
export const platformNav: NavItem[] = [
  {
    to: "/platform",
    label: "Dashboard",
    icon: LayoutDashboard,
    required_perm: "platform.users.read",
  },
  {
    to: "/platform/users",
    label: "Users",
    icon: Users,
    required_perm: "platform.users.read",
  },
  {
    to: "/platform/clients",
    label: "Clients",
    icon: Building2,
    required_perm: "platform.clients.read",
  },
  {
    to: "/platform/settings",
    label: "Settings",
    icon: Settings,
    required_perm: "platform.settings.read",
  },
];

/**
 * Workspace-shell nav. The Link `to` for these items is built at render time
 * by prefixing `/workspace/<id>`; the `to` here is the suffix only.
 */
export const workspaceNav: NavItem[] = [
  {
    to: "",
    label: "Overview",
    icon: LayoutDashboard,
    required_perm: "workspace.members.read",
  },
  {
    to: "/members",
    label: "Members",
    icon: Users,
    required_perm: "workspace.members.read",
  },
  {
    to: "/roles",
    label: "Roles",
    icon: Shield,
    required_perm: "workspace.roles.manage",
  },
  {
    to: "/audit-log",
    label: "Audit log",
    icon: ScrollText,
    required_perm: "workspace.audit.read",
  },
  {
    to: "/settings",
    label: "Settings",
    icon: Settings,
    required_perm: "workspace.settings.read",
  },
];
```

- [ ] **Step 2: Write the failing PlatformSidebar test**

```tsx
// apps/web/src/components/platform-sidebar.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { SidebarProvider } from "@/components/ui/sidebar";
import { PlatformSidebar } from "@/components/platform-sidebar";
import { routeTree } from "@/routeTree.gen";

function renderSidebar(me: {
  platform_permissions: string[];
}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["me"], {
    user_id: "u",
    email: "x@x.com",
    platform: { role: "admin", is_active: true },
    platform_permissions: me.platform_permissions,
    tenants: [],
    pending_invite: null,
  });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/platform"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
      <SidebarProvider>
        <PlatformSidebar />
      </SidebarProvider>
    </QueryClientProvider>,
  );
}

describe("PlatformSidebar", () => {
  it("renders only Dashboard + Users when only platform.users.read is granted", () => {
    renderSidebar({ platform_permissions: ["platform.users.read"] });
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Users")).toBeInTheDocument();
    expect(screen.queryByText("Clients")).toBeNull();
    expect(screen.queryByText("Settings")).toBeNull();
  });

  it("renders Settings when platform.settings.read is granted", () => {
    renderSidebar({
      platform_permissions: ["platform.users.read", "platform.settings.read"],
    });
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pnpm --filter @xtrusio/web test --run src/components/platform-sidebar.test.tsx`
Expected: FAIL with "Cannot find module '@/components/platform-sidebar'".

- [ ] **Step 4: Implement `PlatformSidebar`**

```tsx
// apps/web/src/components/platform-sidebar.tsx
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { platformNav } from "@/lib/nav";
import { hasPlatformPerm, useMe } from "@/lib/me-adapter";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";

export function PlatformSidebar() {
  const { location } = useRouterState();
  const { me } = useMe();
  const items = platformNav.filter((n) => hasPlatformPerm(me, n.required_perm));

  return (
    <Sidebar variant="inset">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-foreground text-background text-xs font-bold">
            X
          </div>
          <span className="text-sm font-semibold tracking-tight">Xtrusio</span>
        </div>
        <WorkspaceSwitcher />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => {
                const Icon = item.icon;
                const active = location.pathname === item.to;
                return (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild isActive={active}>
                      <Link to={item.to}>
                        <Icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  );
}
```

> `WorkspaceSwitcher` is created in Slice D. To keep tests green while it's not implemented yet, ship a minimal stub now and replace it in Slice D. Add the stub before running the test:
>
> Create `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/workspace-switcher.tsx` with:
> ```tsx
> // Slice D replaces this with the real implementation.
> export function WorkspaceSwitcher() { return null; }
> ```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pnpm --filter @xtrusio/web test --run src/components/platform-sidebar.test.tsx`
Expected: PASS — both cases green.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/nav.ts apps/web/src/components/platform-sidebar.tsx apps/web/src/components/platform-sidebar.test.tsx apps/web/src/components/workspace-switcher.tsx
git commit -m "feat(web): permission-driven PlatformSidebar + workspaceNav catalog"
```

### Task C3: Build `WorkspaceSidebar` (TDD)

**Files:**
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/workspace-sidebar.tsx`
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/workspace-sidebar.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/workspace-sidebar.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { SidebarProvider } from "@/components/ui/sidebar";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { routeTree } from "@/routeTree.gen";

function renderSidebar(workspacePerms: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["me"], {
    user_id: "u",
    email: "x@x.com",
    platform: null,
    platform_permissions: [],
    tenants: [
      {
        id: "t1",
        slug: "acme",
        name: "Acme",
        role: "owner",
        permissions: workspacePerms,
      },
    ],
    pending_invite: null,
  });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/workspace/t1"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
      <SidebarProvider>
        <WorkspaceSidebar workspaceId="t1" />
      </SidebarProvider>
    </QueryClientProvider>,
  );
}

describe("WorkspaceSidebar", () => {
  it("renders Overview + Members when only workspace.members.read is granted", () => {
    renderSidebar(["workspace.members.read"]);
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.queryByText("Roles")).toBeNull();
    expect(screen.queryByText("Audit log")).toBeNull();
  });

  it("renders Audit log when workspace.audit.read is granted", () => {
    renderSidebar(["workspace.members.read", "workspace.audit.read"]);
    expect(screen.getByText("Audit log")).toBeInTheDocument();
  });

  it("renders the workspace name in the header", () => {
    renderSidebar(["workspace.members.read"]);
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `pnpm --filter @xtrusio/web test --run src/components/workspace-sidebar.test.tsx`
Expected: FAIL with "Cannot find module '@/components/workspace-sidebar'".

- [ ] **Step 3: Implement `WorkspaceSidebar`**

```tsx
// apps/web/src/components/workspace-sidebar.tsx
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { workspaceNav } from "@/lib/nav";
import { findTenant, hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";

export function WorkspaceSidebar({ workspaceId }: { workspaceId: string }) {
  const { location } = useRouterState();
  const { me } = useMe();
  const tenant = findTenant(me, workspaceId);
  const items = workspaceNav.filter((n) => hasWorkspacePerm(me, workspaceId, n.required_perm));
  const base = `/workspace/${workspaceId}`;

  return (
    <Sidebar variant="inset">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-foreground text-background text-xs font-bold">
            {(tenant?.name ?? "?").slice(0, 1).toUpperCase()}
          </div>
          <span className="text-sm font-semibold tracking-tight truncate">
            {tenant?.name ?? "Workspace"}
          </span>
        </div>
        <WorkspaceSwitcher />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => {
                const fullPath = `${base}${item.to}`;
                const active = location.pathname === fullPath;
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={fullPath}>
                    <SidebarMenuButton asChild isActive={active}>
                      <Link to={fullPath}>
                        <Icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  );
}
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `pnpm --filter @xtrusio/web test --run src/components/workspace-sidebar.test.tsx`
Expected: PASS — all 3 cases green.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/workspace-sidebar.tsx apps/web/src/components/workspace-sidebar.test.tsx
git commit -m "feat(web): permission-driven WorkspaceSidebar"
```

### Task C4: Add the Platform shell layout route + verify the existing pages mount

**Files:**
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/routes/_app.platform.tsx`

- [ ] **Step 1: Write the layout route**

```tsx
// apps/web/src/routes/_app.platform.tsx
import { Outlet, createFileRoute } from "@tanstack/react-router";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { PlatformSidebar } from "@/components/platform-sidebar";
import { AppTopbar } from "@/components/app-topbar";

function PlatformShell() {
  return (
    <SidebarProvider>
      <PlatformSidebar />
      <SidebarInset>
        <AppTopbar />
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}

export const Route = createFileRoute("/_app/platform")({
  component: PlatformShell,
});
```

- [ ] **Step 2: Regenerate the route tree by building**

Run: `pnpm --filter @xtrusio/web build`
Expected: build succeeds. The autogenerated `routeTree.gen.ts` now includes `/_app/platform`, `/_app/platform/`, `/_app/platform/users`, `/_app/platform/clients`, `/_app/platform/clients/$slug/users`, `/_app/platform/settings`.

> If the build fails because `app-topbar.tsx` still references `findLabel` against the old `platformNav` items pointing at `/` etc., proceed to Task C6 — the AppTopbar update — and rerun the build.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/routes/_app.platform.tsx apps/web/src/routeTree.gen.ts
git commit -m "feat(web): _app.platform shell route with PlatformSidebar"
```

### Task C5: Add the Workspace shell layout + placeholder children

**Files:**
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.tsx`
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.index.tsx`
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.members.tsx`
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.roles.tsx`
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.audit-log.tsx`
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx`

- [ ] **Step 1: Write the layout route**

```tsx
// apps/web/src/routes/_app.workspace.$workspaceId.tsx
import { Outlet, createFileRoute, useParams } from "@tanstack/react-router";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { AppTopbar } from "@/components/app-topbar";

function WorkspaceShell() {
  const { workspaceId } = useParams({ from: "/_app/workspace/$workspaceId" });
  return (
    <SidebarProvider>
      <WorkspaceSidebar workspaceId={workspaceId} />
      <SidebarInset>
        <AppTopbar />
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}

export const Route = createFileRoute("/_app/workspace/$workspaceId")({
  component: WorkspaceShell,
});
```

- [ ] **Step 2: Write the five child pages (placeholders that show the shell is mounted)**

```tsx
// apps/web/src/routes/_app.workspace.$workspaceId.index.tsx
import { createFileRoute, useParams } from "@tanstack/react-router";
import { LayoutDashboard } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { findTenant, useMe } from "@/lib/me-adapter";

export const Route = createFileRoute("/_app/workspace/$workspaceId/")({
  component: WorkspaceOverview,
});

function WorkspaceOverview() {
  const { workspaceId } = useParams({ from: "/_app/workspace/$workspaceId/" });
  const { me } = useMe();
  const t = findTenant(me, workspaceId);
  return (
    <>
      <PageHeader
        title={t?.name ?? "Workspace"}
        description="Workspace overview. Activity, recent invites and member growth show up here once P6c lands."
      />
      <EmptyState
        icon={LayoutDashboard}
        title="Workspace ready"
        description="Use the sidebar to manage Members, Roles, the Audit log and Settings."
      />
    </>
  );
}
```

```tsx
// apps/web/src/routes/_app.workspace.$workspaceId.members.tsx
import { createFileRoute } from "@tanstack/react-router";
import { Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/_app/workspace/$workspaceId/members")({
  component: MembersPage,
});

function MembersPage() {
  return (
    <>
      <PageHeader
        title="Members"
        description="People with access to this workspace. Roles and grants are managed here."
      />
      <EmptyState
        icon={Users}
        title="Members management ships in P6c"
        description="The backend endpoints already exist — this UI consumes /api/workspaces/$wid/members in the next phase."
      />
    </>
  );
}
```

```tsx
// apps/web/src/routes/_app.workspace.$workspaceId.roles.tsx
import { createFileRoute } from "@tanstack/react-router";
import { Shield } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/_app/workspace/$workspaceId/roles")({
  component: RolesPage,
});

function RolesPage() {
  return (
    <>
      <PageHeader
        title="Roles"
        description="Custom workspace roles and their permission sets."
      />
      <EmptyState
        icon={Shield}
        title="Roles management ships in P6c"
        description="Backed by /api/workspaces/$wid/roles."
      />
    </>
  );
}
```

```tsx
// apps/web/src/routes/_app.workspace.$workspaceId.audit-log.tsx
import { createFileRoute } from "@tanstack/react-router";
import { ScrollText } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/_app/workspace/$workspaceId/audit-log")({
  component: AuditLogPage,
});

function AuditLogPage() {
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every RBAC mutation in this workspace, in reverse chronological order."
      />
      <EmptyState
        icon={ScrollText}
        title="Audit log ships in P6c"
        description="Backed by /api/workspaces/$wid/audit-log (cursor paginated)."
      />
    </>
  );
}
```

```tsx
// apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx
import { createFileRoute } from "@tanstack/react-router";
import { Settings } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/_app/workspace/$workspaceId/settings")({
  component: WorkspaceSettingsPage,
});

function WorkspaceSettingsPage() {
  return (
    <>
      <PageHeader
        title="Workspace settings"
        description="Per-workspace configuration. Visible to anyone with workspace.settings.read."
      />
      <EmptyState
        icon={Settings}
        title="Settings ship in P6c"
        description="Backed by /api/workspaces/$wid/settings."
      />
    </>
  );
}
```

- [ ] **Step 3: Regenerate the route tree by building**

Run: `pnpm --filter @xtrusio/web build`
Expected: build succeeds. `routeTree.gen.ts` now includes `/_app/workspace/$workspaceId` and the five children.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/routes/_app.workspace.* apps/web/src/routeTree.gen.ts
git commit -m "feat(web): _app.workspace.\$workspaceId shell with placeholder pages"
```

### Task C6: Update `AppTopbar` to reflect both shells

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/app-topbar.tsx` (entire file)

- [ ] **Step 1: Replace the file**

```tsx
// apps/web/src/components/app-topbar.tsx
import { useRouterState } from "@tanstack/react-router";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { SearchTrigger } from "@/components/search-trigger";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { platformNav, workspaceNav } from "@/lib/nav";
import { findTenant, useMe } from "@/lib/me-adapter";

function platformLabel(pathname: string): string {
  if (pathname === "/platform") return "Platform";
  const item = platformNav.find((n) => n.to === pathname);
  return item?.label ?? pathname.replace(/^\/platform\/?/, "");
}

function workspaceLabel(pathname: string, workspaceId: string): string {
  const suffix = pathname.replace(`/workspace/${workspaceId}`, "");
  if (suffix === "" || suffix === "/") return "Overview";
  const item = workspaceNav.find((n) => n.to === suffix);
  return item?.label ?? suffix.replace(/^\//, "");
}

export function AppTopbar() {
  const { location } = useRouterState();
  const { me } = useMe();
  const path = location.pathname;

  let scopeLabel = "Xtrusio";
  let pageLabel = path.replace(/^\//, "");

  if (path === "/platform" || path.startsWith("/platform/")) {
    scopeLabel = "Platform";
    pageLabel = platformLabel(path);
  } else {
    const m = /^\/workspace\/([^/]+)/.exec(path);
    if (m) {
      const wid = m[1] ?? "";
      const t = findTenant(me, wid);
      scopeLabel = t?.name ?? "Workspace";
      pageLabel = workspaceLabel(path, wid);
    }
  }

  return (
    <header className="bg-background sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/">{scopeLabel}</BreadcrumbLink>
          </BreadcrumbItem>
          {pageLabel && pageLabel !== scopeLabel && (
            <>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{pageLabel}</BreadcrumbPage>
              </BreadcrumbItem>
            </>
          )}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="ml-auto flex items-center gap-2">
        <SearchTrigger />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/app-topbar.tsx
git commit -m "refactor(web): topbar label reflects platform vs workspace scope"
```

### Task C7: Update `app-shell-structure.test.tsx` to cover both shells

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/app-shell-structure.test.tsx` (entire file)

- [ ] **Step 1: Replace the file**

```tsx
// apps/web/src/components/app-shell-structure.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { AuthProvider } from "@/lib/auth";
import { routeTree } from "@/routeTree.gen";

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: { session: { access_token: "test", user: { id: "u1", email: "test@example.com" } } },
      }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signInWithPassword: vi.fn(),
      signOut: vi.fn(),
    },
  },
}));

vi.mock("@/lib/api", () => ({
  fetchMe: vi.fn().mockResolvedValue({
    user_id: "u1",
    email: "test@example.com",
    platform: { role: "super_admin", is_active: true },
    platform_permissions: [
      "platform.users.read",
      "platform.clients.read",
      "platform.settings.read",
    ],
    tenants: [
      {
        id: "t1",
        slug: "acme",
        name: "Acme",
        role: "owner",
        permissions: ["workspace.members.read", "workspace.audit.read"],
      },
    ],
    pending_invite: null,
  }),
  fetchSignupStatus: vi.fn().mockResolvedValue({ signups_enabled: false }),
}));

function renderAt(initial: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initial] }),
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ThemeProvider attribute="class" defaultTheme="system">
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

const SIDEBAR = '[data-slot="sidebar"]';

describe("app shell boundary", () => {
  it("renders the platform sidebar on /platform", async () => {
    renderAt("/platform");
    await screen.findByRole("heading", { name: /welcome to xtrusio/i }, { timeout: 3000 });
    expect(document.querySelector(SIDEBAR)).not.toBeNull();
    // Platform-only nav item present
    expect(screen.getByText("Clients")).toBeInTheDocument();
  });

  it("renders the workspace sidebar on /workspace/<id>", async () => {
    renderAt("/workspace/t1");
    await screen.findByText(/workspace ready/i, undefined, { timeout: 3000 });
    expect(document.querySelector(SIDEBAR)).not.toBeNull();
    // Workspace-only nav items present
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.getByText("Audit log")).toBeInTheDocument();
    // Platform-only items absent
    expect(screen.queryByText("Clients")).toBeNull();
  });

  it("does NOT render the sidebar on /sign-in (shell-bleed guard)", async () => {
    renderAt("/sign-in");
    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(document.querySelector(SIDEBAR)).toBeNull();
  });
});
```

> The platform dashboard moved to `_app.platform.index.tsx`; its heading is still "Welcome to Xtrusio" from the original `_app.index.tsx` body. The workspace overview placeholder uses the heading "Workspace ready". Both are unique strings.

- [ ] **Step 2: Run the test**

Run: `pnpm --filter @xtrusio/web test --run src/components/app-shell-structure.test.tsx`
Expected: PASS — all 3 cases green.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/app-shell-structure.test.tsx
git commit -m "test(web): shell-structure covers both platform and workspace shells"
```

---

## Slice D — Workspace Switcher

**Goal:** Replace the `workspace-switcher.tsx` stub with a real dropdown that lists `me.tenants[]` + "Platform admin" (only when `me.platform != null`), navigates on selection, and persists last-selected to localStorage.

### Task D1: Write the failing test

**Files:**
- Create: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/workspace-switcher.test.tsx`

- [ ] **Step 1: Write the spec**

```tsx
// apps/web/src/components/workspace-switcher.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";

const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
  useRouterState: () => ({ location: { pathname: "/platform" } }),
}));

import { WorkspaceSwitcher } from "./workspace-switcher";
import { readLastWorkspace } from "@/lib/last-workspace";

function renderSwitcher(me: {
  platform: { role: "super_admin"; is_active: true } | null;
  tenants: { id: string; slug: string; name: string; role: "owner"; permissions: string[] }[];
}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["me"], {
    user_id: "u",
    email: "x@x.com",
    platform: me.platform,
    platform_permissions: me.platform ? ["platform.users.read"] : [],
    tenants: me.tenants,
    pending_invite: null,
  });
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceSwitcher />
    </QueryClientProvider>,
  );
}

describe("WorkspaceSwitcher", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    window.localStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("lists every tenant in the dropdown", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: { role: "super_admin", is_active: true },
      tenants: [
        { id: "t1", slug: "acme", name: "Acme", role: "owner", permissions: [] },
        { id: "t2", slug: "beta", name: "Beta Co", role: "owner", permissions: [] },
      ],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Beta Co")).toBeInTheDocument();
  });

  it("shows 'Platform admin' only when me.platform is present", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: { role: "super_admin", is_active: true },
      tenants: [],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    expect(screen.getByText(/platform admin/i)).toBeInTheDocument();
  });

  it("hides 'Platform admin' when me.platform is null", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: null,
      tenants: [{ id: "t1", slug: "acme", name: "Acme", role: "owner", permissions: [] }],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    expect(screen.queryByText(/platform admin/i)).toBeNull();
  });

  it("navigates to /workspace/<id> and persists last-selected on tenant click", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: { role: "super_admin", is_active: true },
      tenants: [{ id: "t1", slug: "acme", name: "Acme", role: "owner", permissions: [] }],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    await user.click(screen.getByText("Acme"));
    expect(navigateMock).toHaveBeenCalledWith({ to: "/workspace/$workspaceId", params: { workspaceId: "t1" } });
    expect(readLastWorkspace()).toBe("t1");
  });

  it("navigates to /platform and persists the platform sentinel on 'Platform admin' click", async () => {
    const user = userEvent.setup();
    renderSwitcher({
      platform: { role: "super_admin", is_active: true },
      tenants: [],
    });
    await user.click(screen.getByRole("button", { name: /switch workspace/i }));
    await user.click(screen.getByText(/platform admin/i));
    expect(navigateMock).toHaveBeenCalledWith({ to: "/platform" });
    expect(readLastWorkspace()).toBe("__platform__");
  });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `pnpm --filter @xtrusio/web test --run src/components/workspace-switcher.test.tsx`
Expected: FAIL — the stub returns `null`, so the button isn't found.

### Task D2: Implement `WorkspaceSwitcher`

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/components/workspace-switcher.tsx` (entire file)

- [ ] **Step 1: Replace the stub with the real implementation**

```tsx
// apps/web/src/components/workspace-switcher.tsx
import { useNavigate } from "@tanstack/react-router";
import { Check, ChevronsUpDown, ShieldCheck, Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useMe } from "@/lib/me-adapter";
import { PLATFORM_SENTINEL, writeLastWorkspace } from "@/lib/last-workspace";

export function WorkspaceSwitcher() {
  const navigate = useNavigate();
  const { me } = useMe();
  if (!me) return null;

  const hasPlatform = me.platform !== null;
  const tenants = me.tenants;
  if (!hasPlatform && tenants.length === 0) return null;

  const goPlatform = () => {
    writeLastWorkspace(PLATFORM_SENTINEL);
    navigate({ to: "/platform" });
  };

  const goWorkspace = (workspaceId: string) => {
    writeLastWorkspace(workspaceId);
    navigate({ to: "/workspace/$workspaceId", params: { workspaceId } });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          aria-label="Switch workspace"
          className="w-full justify-between gap-2"
        >
          <span className="truncate text-sm">Switch workspace</span>
          <ChevronsUpDown className="h-4 w-4 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        {hasPlatform && (
          <>
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Platform
            </DropdownMenuLabel>
            <DropdownMenuItem onClick={goPlatform} className="gap-2">
              <ShieldCheck className="h-4 w-4" />
              <span>Platform admin</span>
              <Check className="ml-auto h-4 w-4 opacity-0" />
            </DropdownMenuItem>
            {tenants.length > 0 && <DropdownMenuSeparator />}
          </>
        )}
        {tenants.length > 0 && (
          <>
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Workspaces
            </DropdownMenuLabel>
            {tenants.map((t) => (
              <DropdownMenuItem key={t.id} onClick={() => goWorkspace(t.id)} className="gap-2">
                <Building2 className="h-4 w-4" />
                <span className="truncate">{t.name}</span>
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 2: Run the tests to confirm they pass**

Run: `pnpm --filter @xtrusio/web test --run src/components/workspace-switcher.test.tsx`
Expected: PASS — all 5 cases green.

- [ ] **Step 3: Run the whole suite for regression**

Run: `pnpm --filter @xtrusio/web test`
Expected: PASS — every existing test still passes.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/workspace-switcher.tsx apps/web/src/components/workspace-switcher.test.tsx
git commit -m "feat(web): workspace switcher with localStorage last-selected"
```

### Task D3: Wire AuthGuard to honour `readLastWorkspace()` when path is `/`

**Files:**
- Modify: `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/route-resolver.ts` (within the "Anything else (notably "/") → default landing." branch, lines near the end)

- [ ] **Step 1: Add an override that honours the last-selected scope on `/`**

Open `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/route-resolver.ts`. Replace this block (the last branch of `resolveRoute`):

```ts
  // Anything else (notably "/") → default landing.
  return { kind: "redirect", to: getDefaultLandingPath(me) };
```

with:

```ts
  // Anything else (notably "/") → honour last-selected scope if it's still valid,
  // otherwise fall back to the default landing.
  if (path === "/") {
    const last = readLastWorkspace();
    if (last === PLATFORM_SENTINEL && me.platform) {
      return { kind: "redirect", to: "/platform" };
    }
    if (last && last !== PLATFORM_SENTINEL && me.tenants.some((t) => t.id === last)) {
      return { kind: "redirect", to: `/workspace/${last}` };
    }
  }
  return { kind: "redirect", to: getDefaultLandingPath(me) };
```

And add the import at the top of the file:

```ts
import { PLATFORM_SENTINEL, readLastWorkspace } from "./last-workspace";
```

- [ ] **Step 2: Extend `route-resolver.test.ts` with two cases**

Append to `/Users/jpsingh/Developer/Projects/xtrusio/apps/web/src/lib/route-resolver.test.ts`, inside the `describe("resolveRoute", ...)` block:

```ts
  it("honours last-selected workspace from localStorage on /", () => {
    window.localStorage.setItem("xtrusio.last-workspace", "t1");
    expect(resolveRoute({ session: "s", me: tenant }, "/")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
    window.localStorage.clear();
  });

  it("falls back to default landing when last-selected workspace is unknown", () => {
    window.localStorage.setItem("xtrusio.last-workspace", "missing");
    expect(resolveRoute({ session: "s", me: tenant }, "/")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
    window.localStorage.clear();
  });
```

- [ ] **Step 3: Run the resolver tests**

Run: `pnpm --filter @xtrusio/web test --run src/lib/route-resolver.test.ts`
Expected: PASS — all 14 cases green.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/route-resolver.ts apps/web/src/lib/route-resolver.test.ts
git commit -m "feat(web): root path honours last-selected workspace from localStorage"
```

---

## Slice Wrap — Full Suite + Review + PR

### Task W1: Run the full local check by the controller (not a subagent)

- [ ] **Step 1: Format check + lint**

Run: `make lint`
Expected: green — `ruff format --check apps/api` and `ruff check apps/api` clean (no API code changed); `pnpm exec turbo run lint` clean (ESLint on `apps/web`).

- [ ] **Step 2: Typecheck**

Run: `make typecheck`
Expected: green — `mypy apps/api` (unchanged) and `tsc -b --noEmit` for `apps/web` + `packages/api-types` clean.

- [ ] **Step 3: Tests**

Run: `make test-clean && make test`
Expected: green — Python suite unchanged; `pnpm exec turbo run test` runs `vitest run` and every spec passes.

- [ ] **Step 4: Build (catches route-tree regeneration drift)**

Run: `pnpm --filter @xtrusio/web build`
Expected: green build; if `routeTree.gen.ts` regenerated with any new content, commit the regeneration:

```bash
git add apps/web/src/routeTree.gen.ts
git diff --cached --quiet || git commit -m "chore(web): regenerate route tree"
```

### Task W2: Opus code review

- [ ] **Step 1: Invoke the `code-review` skill against the working tree.**

Per `feedback_lean_review_workflow`: ONE final code-quality review with Opus. Address any findings inline; commit fixes as small follow-ups.

### Task W3: Open the PR

- [ ] **Step 1: Push the branch + open the PR**

```bash
git push -u origin rbac-p6b-frontend-shells
gh pr create \
  --title "feat(rbac): P6b — permission-driven nav + platform/workspace shells + switcher" \
  --body-file docs/superpowers/PR-rbac-p6b-body.md
```

- [ ] **Step 2: Write the PR body** at `docs/superpowers/PR-rbac-p6b-body.md` summarising: pinned `/me` contract (`@xtrusio/api-types/me.ts`), me-adapter API (`hasPlatformPerm`, `hasWorkspacePerm`, `useMe`), permission-driven nav, two physically-separate shells (`_app.platform.*` and `_app.workspace.$workspaceId.*`), workspace switcher with localStorage. Note that the workspace pages are placeholders (P6c implements the bodies). Note the late cleanup gated on this PR (HANDOFF item 6 — drop enum columns).

- [ ] **Step 3: Merge once green**

```bash
gh pr view <n> --json state  # expect MERGED after `gh pr merge`
gh pr merge <n> --squash --delete-branch
```

### Task W4: Update HANDOFF

- [ ] **Step 1: Edit `docs/superpowers/HANDOFF.md`**

Mark P6b DRAINED in the NEXT block; pivot the next pointer to P6c. Reference the merged PR and the plan path.

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(handoff): mark P6b merged; pivot to P6c"
git push
```

---

## Self-Review

**Spec coverage (HANDOFF §NEXT item 4):**

1. **Pinned `/me` effective-perms TS contract in `packages/api-types/src/me.ts`** — Task A1. Mirrors `apps/api/.../schemas/me.py` exactly with `platform_permissions: PermissionKey[]` and `tenants[].permissions: PermissionKey[]`, enums kept additively.
2. **Legacy-compat adapter** — Tasks A4 + A5. `hasPlatformPerm`, `hasWorkspacePerm`, `findTenant`, `getDefaultLandingPath`, `useMe`. Enum-path reads (`me.platform.role`) keep working because the enum fields stay on the type; the adapter only adds permission helpers.
3. **Permission-driven nav** — Task C2. `NavItem.required_perm` added, both `platformNav` and `workspaceNav` tag every item, sidebars filter via the adapter.
4. **Two physically-separate shells** — Tasks C1, C4, C5, C7. `_app.tsx` reduced to pass-through; `_app.platform.tsx` mounts `PlatformSidebar`; `_app.workspace.$workspaceId.tsx` mounts `WorkspaceSidebar`; placeholder children for Overview / Members / Roles / Audit log / Settings ship with the shell.
5. **Workspace switcher** — Tasks D1, D2, D3. Dropdown listing `me.tenants[]` + Platform admin entry (gated on `me.platform`), navigation, localStorage persistence, root `/` honours the last-selected scope.

**Placeholder scan:** every code step has a complete code block. No TBD/TODO/implement-later strings. Every test step shows the assertions. Every shell file imports concrete modules created in earlier slices. The only intentional "placeholder" is the page bodies for the workspace shell — explicitly scoped to P6c per HANDOFF item 5, and each renders a real `PageHeader` + `EmptyState` so no half-built UI ships.

**Type consistency:** `MeResponse`/`PlatformContext`/`TenantContext`/`PendingInvite`/`PermissionKey` are defined once in `packages/api-types/src/me.ts` and re-exported from `packages/api-types/src/index.ts`. `apps/web` imports them via `@xtrusio/api-types`. `route-resolver.ts` re-exports `MeResponse` as a `type` only so existing `import type { MeResponse } from "./route-resolver"` sites are not broken on the way. `hasPlatformPerm(me, key)` and `hasWorkspacePerm(me, workspaceId, key)` use identical argument order across the adapter, the sidebars, the switcher, and the resolver. The `PLATFORM_SENTINEL` constant is declared once in `last-workspace.ts` and reused by `workspace-switcher.tsx` + `route-resolver.ts`. The TanStack `navigate({ to: "/workspace/$workspaceId", params: { workspaceId } })` shape is used identically in the switcher test and the switcher implementation.

**Hard-constraint compliance:**

- `feedback_frontend_typescript_only`: every new file is `.ts` or `.tsx`. No `.js`/`.jsx`/`.mjs`/`.cjs`.
- `feedback_no_demo_data`: zero seed data; tests use `qc.setQueryData(["me"], ...)` to hand-roll fixtures.
- `feedback_enterprise_grade_no_copy`: each placeholder page renders a real `PageHeader` + `EmptyState` describing the next phase; no Lorem ipsum, no "Coming soon!!1" copy.
- `feedback_no_hardcoded_config`: no env-varying values are introduced — `VITE_API_BASE_URL` etc. continue to flow through the existing `import.meta.env` shape declared in `apps/web/src/vite-env.d.ts`.
- `feedback_per_page_theme_scope`: this plan does NOT add any ancestor `bg-background` or padding around scoped routes. The two shells own their own `SidebarProvider` tree; `_app.tsx` is now a bare `<Outlet />` (no styling).
- `feedback_auth_aurora_with_color`: auth pages are untouched.
- `feedback_lean_review_workflow`: Slice Wrap has ONE controller-run `make lint` + `make typecheck` + `make test` gate, ONE Opus review, ONE PR.

Plan ready.
