# RBAC P6c — Slice 3: Workspace Members port + platform nav + cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the last workspace placeholder route (Members — invite UI only, with an explicit "member listing ships in P6d" notice), add Roles + Audit log entries to the platform sidebar (so the Slice-1/2 pages are reachable from the nav), rewrite `UserMenu` to use the shared `useMe()` adapter, convert `tenant-users-page`'s last enum-role check to `hasWorkspacePerm`, and tighten the placeholder copy on the Workspace Settings page (drop the stale `/api/workspaces/$wid/settings` reference). Pure frontend — zero backend changes.

**Architecture:** No new architecture. This slice consumes the building blocks added by Slices 1 and 2 (`<Forbidden />`, `qk`, `lib/error-messages`, `me-adapter`) and the existing P3b-era invite endpoints (`postTenantInvite`, `fetchTenantInvites`, `deleteTenantInvite`) for the Workspace Members page. The new `<WorkspaceMembersPage>` ports the InviteDialog flow from `tenant-users-page` (which lives under `/platform/clients/$slug/users` and is a platform-admin view of a tenant's invites) — the workspace-scope page is a different surface and consumer that needs to live under `/workspace/$wid/members`.

**Tech Stack:** TypeScript (strict), React 19, TanStack Router (file-based), TanStack Query v5, Vitest 2, React Testing Library 16, Tailwind 4, shadcn/Radix primitives.

**Depends on:** Slice 1 (`<Forbidden />`, `qk`, error-messages mappings) AND Slice 2 (no direct API import dependency but the audit log page must exist before adding the platform-nav `Audit log` item).

---

## File Structure

### Create

| Path | Purpose |
|---|---|
| `apps/web/src/components/workspace-members-page.tsx` | Ports the existing InviteDialog flow from `tenant-users-page` to be workspace-id-driven (uses `qk.workspaceInvites(wid)` cache key). |
| `apps/web/src/components/workspace-members-page.test.tsx` | Gate, invite/revoke happy paths, `canInvite` from `hasWorkspacePerm(me, wid, "workspace.members.invite")`, "ships in P6d" notice present. |

### Modify

| Path | Lines | Change |
|---|---|---|
| `apps/web/src/lib/nav.ts` | 23-48 (the `platformNav` array) | Add Roles + Audit log entries gated by `platform.roles.manage` and `platform.audit.read`. |
| `apps/web/src/components/platform-sidebar.test.tsx` | append | Add an assertion that the new Roles / Audit log items appear/hide based on `hasPlatformPerm`. |
| `apps/web/src/components/user-menu.tsx` | 1-63 (full rewrite) | Drop local `type Me`; drop the inline `useQuery(["me"])`; consume `useMe()` from `@/lib/me-adapter`; render Badge from `me.platform.role` (kept additive on MeResponse). |
| `apps/web/src/components/tenant-users-page.tsx` | 125 (the `canInvite` line) | Replace `myTenant.role === "owner" \|\| myTenant.role === "admin"` with `hasWorkspacePerm(me, myTenant.id, "workspace.members.invite")`. Use `useMe()` for `me` rather than the inline `useQuery`. |
| `apps/web/src/components/tenant-users-page.test.tsx` | extend | Verify `canInvite` flips based on the workspace permissions array, not the legacy enum role. |
| `apps/web/src/routes/_app.workspace.$workspaceId.members.tsx` | 1-24 (full file) | Replace placeholder with file-route mounting `<WorkspaceMembersPage workspaceId={...} />`. |
| `apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx` | 16-21 (description copy) | Drop the `/api/workspaces/$wid/settings` reference in the EmptyState description; the endpoint doesn't exist, mentioning it is misleading. Replace with "Workspace-scoped settings ship in P6d." |

### Notes

- `apps/web/src/components/tenant-users-page.tsx` stays as the **platform-admin view** of a tenant's invites under `/platform/clients/$slug/users`. The new `workspace-members-page.tsx` is a separate, workspace-owner-driven view under `/workspace/$wid/members`. They are not consolidated — they have different consumers and different gating, and consolidating them now (without a real member-listing endpoint) would be a premature abstraction.
- `me-adapter.ts` already exports `useMe()` that wraps the shared `["me"]` query. The Slice-3 cleanups all consume it.
- The `Tenants` (workspaces) cache key is `qk.workspaceInvites(wid)` — defined in Slice 1; do not redefine it inline.
- No backend changes. Alembic head stays at `0009`.

---

## Slice 3A — Extend platform nav

### Task 3A.1: Add Roles + Audit log to `platformNav`

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/lib/nav.ts` (lines 23-48)

- [ ] **Step 1: Add the icons import**

Open `apps/web/src/lib/nav.ts`. The existing import already pulls `Shield, ScrollText` from `lucide-react` (used by the workspaceNav further down). No new import needed.

- [ ] **Step 2: Extend the `platformNav` array**

Replace the existing `platformNav` array (lines 23-48) with:

```ts
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
    to: "/platform/roles",
    label: "Roles",
    icon: Shield,
    required_perm: "platform.roles.manage",
  },
  {
    to: "/platform/audit-log",
    label: "Audit log",
    icon: ScrollText,
    required_perm: "platform.audit.read",
  },
  {
    to: "/platform/settings",
    label: "Settings",
    icon: Settings,
    required_perm: "platform.settings.read",
  },
];
```

- [ ] **Step 3: Extend the `platform-sidebar.test.tsx` to cover the new items**

The existing tests in this file prime the `["me"]` query cache via `qc.setQueryData(...)` and render through `RouterContextProvider` + `SidebarProvider`. The new assertions follow the same pattern — append at the bottom of `apps/web/src/components/platform-sidebar.test.tsx`:

```tsx
describe("PlatformSidebar — Slice 3 nav additions", () => {
  it("renders Roles only when platform.roles.manage is granted", () => {
    const { rerender } = renderSidebar({
      platform_permissions: ["platform.users.read"],
    });
    expect(screen.queryByText("Roles")).toBeNull();

    // Re-render with the perm granted — easiest is a fresh render() call
    // since the existing tests don't share QueryClient state between cases.
    rerender(<></>);
    renderSidebar({
      platform_permissions: ["platform.users.read", "platform.roles.manage"],
    });
    expect(screen.getByText("Roles")).toBeInTheDocument();
  });

  it("renders Audit log only when platform.audit.read is granted", () => {
    renderSidebar({ platform_permissions: ["platform.users.read"] });
    expect(screen.queryByText("Audit log")).toBeNull();

    renderSidebar({
      platform_permissions: ["platform.users.read", "platform.audit.read"],
    });
    expect(screen.getByText("Audit log")).toBeInTheDocument();
  });
});
```

If `renderSidebar` does not return a `rerender` (it isn't always exported by Testing Library when you wrap the call), the simpler structure is two separate `it("…hidden…")` and `it("…shown…")` cases. Pick whichever shape the existing two assertions in this file already use — copy it.

- [ ] **Step 4: Run tests**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/platform-sidebar.test.tsx`
Expected: all PASS (the two new assertions + every existing one).

- [ ] **Step 5: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/nav.ts apps/web/src/components/platform-sidebar.test.tsx
git commit -m "feat(web): platform nav exposes Roles + Audit log"
```

---

## Slice 3B — `<UserMenu />` rewrite

### Task 3B.1: Rewrite `<UserMenu />` to consume `useMe()`

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/user-menu.tsx` (lines 1-63, full rewrite)

- [ ] **Step 1: Read the current file**

Run: `cat apps/web/src/components/user-menu.tsx`
Note the local `type Me`, the inline `useQuery(["me"], …)`, and the rendered Badge driven by `me.role`.

- [ ] **Step 2: Replace the full file**

```tsx
import { LogOut } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useMe } from "@/lib/me-adapter";

export function UserMenu() {
  const { user, signOut } = useAuth();
  const { me } = useMe();

  const initial = (me?.email ?? user?.email ?? "?").slice(0, 1).toUpperCase();
  const role = me?.platform?.role;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label="User menu"
          className="rounded-full"
        >
          <Avatar className="h-8 w-8">
            <AvatarFallback>{initial}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium">
              {me?.email ?? user?.email ?? "Loading…"}
            </span>
            {role && (
              <Badge variant="secondary" className="w-fit text-xs">
                {role.replace("_", " ")}
              </Badge>
            )}
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void signOut()}>
          <LogOut className="mr-2 h-4 w-4" />
          <span>Sign out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 3: Verify the file no longer imports `useQuery` or `apiFetch`**

Run:
```bash
grep -E "useQuery|apiFetch|type Me" apps/web/src/components/user-menu.tsx
```
Expected: no matches. (If the old `type Me` lingered as a leftover, remove it now.)

- [ ] **Step 4: Update / write the matching test if it exists**

Run: `ls apps/web/src/components/user-menu.test.tsx 2>/dev/null && echo "test exists" || echo "test does not exist"`

If the test does not exist, create it:

```tsx
// apps/web/src/components/user-menu.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse } from "@xtrusio/api-types";
import { UserMenu } from "./user-menu";

const ME: MeResponse = {
  user_id: "u-1",
  email: "super@xtrusio.com",
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.users.read"],
  tenants: [],
  pending_invite: null,
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, fetchMe: vi.fn() };
});

const signOut = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ user: { email: "super@xtrusio.com" }, signOut }),
}));

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
});

function renderWith(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <UserMenu />
    </QueryClientProvider>,
  );
}

describe("<UserMenu />", () => {
  it("renders the email and the platform-role badge from useMe()", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await userEvent.click(screen.getByRole("button", { name: /user menu/i }));
    await waitFor(() => {
      expect(screen.getByText("super@xtrusio.com")).toBeInTheDocument();
      expect(screen.getByText(/super admin/i)).toBeInTheDocument();
    });
  });

  it("renders without a Badge when me.platform is null", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue({
      ...ME,
      platform: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await userEvent.click(screen.getByRole("button", { name: /user menu/i }));
    await waitFor(() =>
      expect(screen.getByText("super@xtrusio.com")).toBeInTheDocument(),
    );
    // The Badge text doesn't render.
    expect(screen.queryByText(/super admin|^admin$|^editor$/i)).toBeNull();
  });

  it("fires signOut on click", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await userEvent.click(screen.getByRole("button", { name: /user menu/i }));
    await userEvent.click(screen.getByText(/sign out/i));
    expect(signOut).toHaveBeenCalled();
  });
});
```

If the test already exists, replace its imports + fixtures to use `MeResponse` from `@xtrusio/api-types` and call `useMe()` (via the same mock pattern). Drop any local `Me` type fixture in favour of the api-types one.

- [ ] **Step 5: Run the test**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/user-menu.test.tsx`
Expected: all PASS.

- [ ] **Step 6: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/user-menu.tsx apps/web/src/components/user-menu.test.tsx
git commit -m "refactor(web): UserMenu consumes useMe(), drops local Me type"
```

---

## Slice 3C — `tenant-users-page` enum → permission conversion

### Task 3C.1: Convert `canInvite` to `hasWorkspacePerm`

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/tenant-users-page.tsx` (lines 109-138 — replace inline `useQuery(["me"])` + `canInvite` computation)
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/tenant-users-page.test.tsx` (extend with permission-driven test cases)

- [ ] **Step 1: Read the current file**

Run: `cat apps/web/src/components/tenant-users-page.tsx`
Note line 125: `const canInvite = myTenant.role === "owner" || myTenant.role === "admin";`

- [ ] **Step 2: Replace the imports**

Open `apps/web/src/components/tenant-users-page.tsx`. At the top of the file, the imports include `useQuery` from `@tanstack/react-query` and `fetchMe` from `@/lib/api`. Replace those with:

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMe, hasWorkspacePerm } from "@/lib/me-adapter";
```

(Leave the `useQuery` import in place only if `useQuery` is still used elsewhere in the file — for the `tenant-invites` query. Confirm via `grep -c "useQuery" apps/web/src/components/tenant-users-page.tsx`.)

Drop:
```tsx
import { fetchMe } from "@/lib/api";
```
(again, only if no other consumer in this file still uses it).

- [ ] **Step 3: Replace the `me` fetch + canInvite computation in `TenantUsersPage`**

Replace the existing `const { data: me } = useQuery(...)` line and the subsequent `canInvite` line with:

```tsx
const { me } = useMe();
const myTenant = me?.tenants.find((t) => t.slug === slug);
const tenantId = myTenant?.id ?? "";
// ... (the existing invites/revoke code is unchanged) ...
if (!myTenant) return null;
const canInvite = hasWorkspacePerm(
  me,
  myTenant.id,
  "workspace.members.invite",
);
```

Remove the legacy `canInvite = myTenant.role === "owner" || myTenant.role === "admin"` line. Also remove the cast `inviterRole={myTenant.role as "owner" | "admin"}` — replace the `InviteTenantDialog` invocation with a version that no longer needs `inviterRole` (the dialog can derive allowed roles from `hasWorkspacePerm` itself, or accept a permission-based prop).

If `InviteTenantDialog`'s internal `inviterRole` enum is load-bearing (it gates which `TenantRole` literal values the user can pick), keep it for now — that role-selector UI is invite-level metadata that lives in the existing P3a-era invite contract and is not part of this slice's cleanup. Pass the existing value through; only the outer `canInvite` gate moves to `hasWorkspacePerm`.

- [ ] **Step 4: Extend the test**

Open `apps/web/src/components/tenant-users-page.test.tsx`. Add (or replace any existing role-based assertion with) two cases:

```tsx
it("renders the Invite button when me has workspace.members.invite for this tenant", async () => {
  // me fixture has tenants[0].permissions including "workspace.members.invite"
  // assertion: getByRole("button", { name: /invite user/i }) appears
});

it("does NOT render the Invite button when me lacks workspace.members.invite", async () => {
  // me fixture has tenants[0].permissions = ["workspace.members.read"]
  // assertion: queryByRole("button", { name: /invite user/i }) is null
});
```

Wire them with the same mock pattern the other tests in the file use (or copy the pattern from `platform-roles-page.test.tsx` from Slice 1). Remove any legacy assertion that branched on `tenants[0].role === "owner"`.

- [ ] **Step 5: Run the test**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/tenant-users-page.test.tsx`
Expected: all PASS, including the two new permission-driven assertions.

- [ ] **Step 6: Verify no remaining enum reads in this file**

Run:
```bash
grep -E '\.role === "(owner|admin|editor|read_only)"' apps/web/src/components/tenant-users-page.tsx
```
Expected: no matches (or only inside the `InviteTenantDialog`'s internal `inviterRole` branching, which is intentional).

- [ ] **Step 7: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/components/tenant-users-page.tsx apps/web/src/components/tenant-users-page.test.tsx
git commit -m "refactor(web): tenant-users-page canInvite via hasWorkspacePerm"
```

---

## Slice 3D — Workspace Members page (invite-only port)

### Task 3D.1: `<WorkspaceMembersPage />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/workspace-members-page.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/workspace-members-page.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/workspace-members-page.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse } from "@xtrusio/api-types";
import { WorkspaceMembersPage } from "./workspace-members-page";

const WID = "wid-1";

const ME_INVITER: MeResponse = {
  user_id: "u-1",
  email: "owner@acme.com",
  platform: null,
  platform_permissions: [],
  tenants: [
    {
      id: WID,
      slug: "acme",
      name: "Acme",
      role: "owner",
      permissions: ["workspace.members.read", "workspace.members.invite"],
    },
  ],
  pending_invite: null,
};

const ME_READ_ONLY: MeResponse = {
  ...ME_INVITER,
  tenants: [
    {
      ...ME_INVITER.tenants[0]!,
      role: "editor",
      permissions: ["workspace.members.read"],
    },
  ],
};

const ME_NO_ACCESS: MeResponse = {
  ...ME_INVITER,
  tenants: [
    {
      ...ME_INVITER.tenants[0]!,
      role: "editor",
      permissions: [],
    },
  ],
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchTenantInvites: vi.fn(),
    postTenantInvite: vi.fn(),
    deleteTenantInvite: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchTenantInvites).mockResolvedValue({ items: [] });
});

function renderWith(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceMembersPage workspaceId={WID} />
    </QueryClientProvider>,
  );
}

describe("<WorkspaceMembersPage />", () => {
  it("renders <Forbidden /> when me lacks workspace.members.read", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_NO_ACCESS);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() =>
      expect(
        screen.getByText(/don't have access|don't have permission/i),
      ).toBeInTheDocument(),
    );
  });

  it("shows the 'ships in P6d' notice", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_READ_ONLY);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(
        screen.getByText(/member listing ships in p6d/i),
      ).toBeInTheDocument();
    });
  });

  it("hides the Invite button when me lacks workspace.members.invite", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_READ_ONLY);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText(/member listing ships in p6d/i));
    expect(
      screen.queryByRole("button", { name: /invite user/i }),
    ).toBeNull();
  });

  it("shows the Invite button + invites list when me has workspace.members.invite", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_INVITER);
    vi.mocked(api.fetchTenantInvites).mockResolvedValue({
      items: [
        {
          id: "inv-1",
          tenant_id: WID,
          email: "guest@acme.com",
          role: "editor",
          expires_at: "2026-06-22T00:00:00Z",
          accepted_at: null,
          revoked_at: null,
          created_at: "2026-05-22T00:00:00Z",
        },
      ],
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /invite user/i }),
      ).toBeInTheDocument();
      expect(screen.getByText("guest@acme.com")).toBeInTheDocument();
    });
  });

  it("revokes an invite and invalidates qk.workspaceInvites(wid)", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_INVITER);
    vi.mocked(api.fetchTenantInvites).mockResolvedValue({
      items: [
        {
          id: "inv-1",
          tenant_id: WID,
          email: "guest@acme.com",
          role: "editor",
          expires_at: "2026-06-22T00:00:00Z",
          accepted_at: null,
          revoked_at: null,
          created_at: "2026-05-22T00:00:00Z",
        },
      ],
    });
    vi.mocked(api.deleteTenantInvite).mockResolvedValue();
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("guest@acme.com"));
    await userEvent.click(screen.getByRole("button", { name: /revoke/i }));
    await waitFor(() => {
      expect(api.deleteTenantInvite).toHaveBeenCalledWith(WID, "inv-1");
    });
    await waitFor(() => {
      expect(vi.mocked(api.fetchTenantInvites)).toHaveBeenCalledTimes(2);
    });
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/workspace-members-page.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the page**

```tsx
// apps/web/src/components/workspace-members-page.tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Info } from "lucide-react";
import type { TenantInvite } from "@/lib/api";
import {
  deleteTenantInvite,
  errorCode,
  fetchTenantInvites,
  postTenantInvite,
} from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { qk } from "@/lib/query-keys";
import {
  findTenant,
  getDefaultLandingPath,
  hasWorkspacePerm,
  useMe,
} from "@/lib/me-adapter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";

type InviteRole = "admin" | "editor" | "read_only";

function InviteDialog({
  workspaceId,
  canPickAdmin,
}: {
  workspaceId: string;
  canPickAdmin: boolean;
}) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InviteRole>(canPickAdmin ? "admin" : "editor");
  const [open, setOpen] = useState(false);
  const allowed: InviteRole[] = canPickAdmin
    ? ["admin", "editor", "read_only"]
    : ["editor", "read_only"];
  const m = useMutation({
    mutationFn: () => postTenantInvite(workspaceId, email, role),
    onSuccess: async () => {
      await qc.invalidateQueries({
        queryKey: qk.workspaceInvites(workspaceId),
      });
      setOpen(false);
      setEmail("");
      setRole(canPickAdmin ? "admin" : "editor");
    },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Invite user</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a user to this workspace</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate();
          }}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">Role</Label>
            <Select
              value={role}
              onValueChange={(v) => setRole(v as InviteRole)}
            >
              <SelectTrigger id="role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {allowed.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {m.error ? (
            <p className="text-sm text-destructive">
              {errorMessage(errorCode(m.error))}
            </p>
          ) : null}
          <Button type="submit" disabled={m.isPending} className="w-full">
            {m.isPending ? "Sending…" : "Send invite"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function WorkspaceMembersPage({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const { me } = useMe();
  if (!hasWorkspacePerm(me, workspaceId, "workspace.members.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body me={me} workspaceId={workspaceId} />;
}

function Body({
  me,
  workspaceId,
}: {
  me: ReturnType<typeof useMe>["me"];
  workspaceId: string;
}) {
  const qc = useQueryClient();
  const tenant = findTenant(me, workspaceId);
  const canInvite = hasWorkspacePerm(
    me,
    workspaceId,
    "workspace.members.invite",
  );
  // "owner" is the workspace governance role; only owner may invite an admin.
  const canPickAdmin = tenant?.role === "owner";

  const { data: invites } = useQuery({
    queryKey: qk.workspaceInvites(workspaceId),
    queryFn: () => fetchTenantInvites(workspaceId),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => deleteTenantInvite(workspaceId, id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: qk.workspaceInvites(workspaceId) }),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${tenant?.name ?? "Workspace"} — Members`}
        description="People with access to this workspace. Invite, list pending invites, and revoke them."
        action={
          canInvite ? (
            <InviteDialog
              workspaceId={workspaceId}
              canPickAdmin={canPickAdmin}
            />
          ) : null
        }
      />
      <section className="rounded-md border bg-muted/30 p-4 text-sm">
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-4 w-4 text-muted-foreground" aria-hidden />
          <p className="text-muted-foreground">
            Member listing ships in P6d. For now you can invite people and
            revoke pending invites; the full member list will appear here once
            the backend{" "}
            <code>GET /api/workspaces/{`{wid}`}/members</code> endpoint lands.
          </p>
        </div>
      </section>
      <section>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">
          Invitations
        </h2>
        {invites && invites.items.length > 0 ? (
          <ul className="divide-y rounded-md border">
            {invites.items.map((i: TenantInvite) => (
              <li
                key={i.id}
                className="flex items-center justify-between p-4"
              >
                <div>
                  <p className="font-medium">{i.email}</p>
                  <p className="text-xs text-muted-foreground">{i.role}</p>
                </div>
                {i.accepted_at ? (
                  <span className="text-xs text-foreground">Accepted</span>
                ) : i.revoked_at ? (
                  <span className="text-xs text-muted-foreground">
                    Revoked
                  </span>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => revoke.mutate(i.id)}
                    disabled={revoke.isPending}
                  >
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No invitations yet.
          </p>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/workspace-members-page.test.tsx`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/workspace-members-page.tsx apps/web/src/components/workspace-members-page.test.tsx
git commit -m "feat(web): <WorkspaceMembersPage /> — invite UI port"
```

### Task 3D.2: Replace the `_app.workspace.$workspaceId.members` placeholder

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.members.tsx` (full file)

- [ ] **Step 1: Write the new file**

```tsx
import { createFileRoute, useParams } from "@tanstack/react-router";
import { WorkspaceMembersPage } from "@/components/workspace-members-page";

export const Route = createFileRoute(
  "/_app/workspace/$workspaceId/members",
)({
  component: RouteComponent,
});

function RouteComponent() {
  const { workspaceId } = useParams({
    from: "/_app/workspace/$workspaceId/members",
  });
  return <WorkspaceMembersPage workspaceId={workspaceId} />;
}
```

- [ ] **Step 2: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/routes/_app.workspace.$workspaceId.members.tsx apps/web/src/routeTree.gen.ts
git commit -m "feat(web): /workspace/\$id/members now consumes <WorkspaceMembersPage />"
```

---

## Slice 3E — Workspace Settings placeholder copy fix

### Task 3E.1: Drop the stale API reference

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx` (lines 15-22, the EmptyState description)

- [ ] **Step 1: Read the current file**

Run: `cat apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx`

- [ ] **Step 2: Replace the EmptyState description**

Replace the existing `description="Backed by /api/workspaces/$wid/settings."` line with:

```tsx
        description="Workspace-scoped settings ship in P6d."
```

(The endpoint doesn't exist; mentioning it in the placeholder copy is misleading.)

- [ ] **Step 3: Run any existing test for this route**

Run: `pnpm --filter @xtrusio/web exec vitest run 2>&1 | grep -E "workspace.settings|workspace settings" || echo "(no targeted test exists; skipping)"`

(There is no targeted test for this placeholder; the change is copy-only. If a snapshot test breaks because of the copy change, update the snapshot.)

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx
git commit -m "docs(web): workspace settings placeholder copy mentions P6d, not a fictional endpoint"
```

---

## Slice 3 Wrap — End-of-slice verification, review, PR, merge

### Task 3W.1: Controller-run end-of-slice gate

- [ ] **Step 1: Reset and run full backend tests**

Run: `STARTUP_RECONCILE_TOLERANT=false make test-clean`
Expected: exit 0. (Slice 3 is pure frontend, but the gate runs the full backend suite to confirm zero regressions from the surrounding context.)

- [ ] **Step 2: Lint + typecheck + frontend test gate**

Run: `STARTUP_RECONCILE_TOLERANT=false make check`
Expected: exit 0.

- [ ] **Step 3: Smoke check manually (USER-DRIVEN)**

User logs in as workspace owner, visits `/workspace/<wid>/members`, sees the "ships in P6d" notice, invites a colleague, sees the invitation appear, revokes it. Logs in as a workspace `editor`, visits `/workspace/<wid>/members`, sees the page (read access) without an Invite button. Logs in as super_admin, opens the user-menu dropdown and confirms email + super_admin badge appear. Visits `/platform`, confirms Roles + Audit log appear in the sidebar.

### Task 3W.2: Opus code-quality review

Controller-run via `/ultrareview`. Apply blocking findings.

### Task 3W.3: Open the PR

- [ ] **Step 1: Write the PR body**

Save to `docs/superpowers/PR-rbac-p6c-slice-3-body.md`:

```markdown
## Summary

- Add `<WorkspaceMembersPage>` at `/workspace/$id/members` — invite-only port from `tenant-users-page` with an explicit "member listing ships in P6d" notice card on the page.
- Add `platformNav` entries for Roles + Audit log so the Slice-1 + Slice-2 pages are reachable.
- Rewrite `<UserMenu>` to consume the shared `useMe()` from `me-adapter` (drops the local `Me` type + duplicate `useQuery(["me"])`).
- Convert `tenant-users-page`'s `canInvite` from `myTenant.role === "owner" | "admin"` to `hasWorkspacePerm(me, tid, "workspace.members.invite")` — completes the in-scope enum→permission conversion called out in the HANDOFF.
- Update the Workspace Settings placeholder copy to drop the stale `/api/workspaces/$wid/settings` reference (that endpoint doesn't exist; it ships with P6d).

Pure frontend. Zero backend changes. Alembic head stays at `0009`.

## Test plan

- [ ] `STARTUP_RECONCILE_TOLERANT=false make test-clean` green
- [ ] `STARTUP_RECONCILE_TOLERANT=false make check` green (ruff check + ruff format --check + mypy --strict + turbo typecheck + vitest)
- [ ] Manual: workspace owner can invite + revoke + see pending invites at `/workspace/<wid>/members`
- [ ] Manual: workspace editor sees the Members page (read access) WITHOUT the Invite button
- [ ] Manual: super_admin sees Roles + Audit log in the platform sidebar; both link to the pages shipped in Slice 1 / 2
- [ ] Manual: UserMenu renders email + role Badge for super_admin; renders email-only for a non-platform user

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "P6c Slice 3 — Members port + platform nav + cleanup" \
  --body "$(cat docs/superpowers/PR-rbac-p6c-slice-3-body.md)"
```

### Task 3W.4: Merge + HANDOFF update — closes P6c

- [ ] **Step 1: Merge**

```bash
gh pr merge <PR#> --squash
gh pr view <PR#> --json state  # confirm "MERGED"
```

- [ ] **Step 2: Update HANDOFF.md — close P6c, pivot to P6d**

Open `docs/superpowers/HANDOFF.md`. Move all three P6c slices into the "Done & merged" table. Rewrite the prose lead-in to reflect that P6c is fully merged. Pivot the "NEXT" block to **P6d**, with these items (taken from spec section 3 and section 8):

- `GET /api/platform/users` (cursor-paginated, gated `platform.users.read`)
- `GET /api/workspaces/{wid}/members` (cursor-paginated, gated `workspace.members.read`)
- `GET/PUT /api/workspaces/{wid}/settings`
- Platform + workspace grant-management UIs (per-user dialog with role multi-select)
- Workspace Settings UI
- Possibly: a tiny `GET /api/.../roles/{id}/grants?count_only` style endpoint so the role-delete dialog can show a precise count (consider, don't commit yet)

Also note the still-deferred LATE cleanup (drop `platform_users.role` / `tenant_memberships.role` columns + enum types — only once P6d's grant UIs are confirmed not to consume `tenants[].role`).

- [ ] **Step 3: Commit + push**

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(handoff): P6c fully merged; pivot NEXT to P6d"
git push
```

---

## Self-review checklist (run before declaring Slice 3 — and all of P6c — done)

- [ ] No remaining `myTenant.role === "owner"|"admin"` patterns in `apps/web/src/components/tenant-users-page.tsx` outside the `InviteTenantDialog`'s `inviterRole` selector (which is the invite-system's role enum, distinct from authorization)
- [ ] `<UserMenu>` no longer has a local `type Me` or a duplicate `useQuery(["me"])`
- [ ] `apps/web/src/lib/nav.ts` exposes Roles + Audit log entries on the platform side, gated by `platform.roles.manage` and `platform.audit.read`
- [ ] Workspace Members page renders for any user with `workspace.members.read`; Invite button only renders for those with `workspace.members.invite`
- [ ] Workspace Settings placeholder no longer references `/api/workspaces/$wid/settings`
- [ ] `make check` exits 0 from a CLEAN DB
- [ ] HANDOFF.md closes P6c, opens P6d
