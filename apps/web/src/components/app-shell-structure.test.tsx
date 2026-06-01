import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { routeTree } from "@/routeTree.gen";
import type { MeResponse } from "@xtrusio/api-types";
import type { Session } from "@supabase/supabase-js";
import { queryClient } from "@/lib/query-client";
import { useAuthStore } from "@/lib/auth-store";

// Each case below sets `session` and `me` via these mutable holders, then we
// reset the supabase + fetchMe mocks in beforeEach. `__root.tsx` already wraps
// the tree with ThemeProvider + QueryClientProvider + AuthProvider — we
// deliberately render the bare RouterProvider here; double-wrapping caused the
// supabase subscription to misfire and the body to come out empty.
//
// `holders` MUST be created with vi.hoisted: the Zustand auth re-arch (#57)
// runs `initAuth()` at module-load, which calls supabase.auth.getSession()
// synchronously while the module graph is still evaluating. vitest hoists the
// vi.mock factories above this declaration, so a plain `const holders` would be
// in the TDZ when getSession's factory reads `holders.session` → "Cannot access
// 'holders' before initialization". vi.hoisted lifts it above the mocks.
const holders = vi.hoisted(() => ({
  session: null as { access_token: string; user: { id: string; email: string } } | null,
  me: null as MeResponse | null,
}));

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi
        .fn()
        .mockImplementation(() => Promise.resolve({ data: { session: holders.session } })),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signInWithPassword: vi.fn(),
      signOut: vi.fn(),
    },
  },
}));

vi.mock("@/lib/api", () => ({
  fetchMe: vi.fn().mockImplementation(() => Promise.resolve(holders.me)),
  fetchSignupStatus: vi.fn().mockResolvedValue({ signups_enabled: false }),
  // The dashboards now fetch stats; these shell-boundary cases only assert the
  // sidebar + empty-state heading, so all-null stats payloads (every metric
  // card omitted) keep the dashboards rendering without coupling to counts.
  fetchPlatformStats: vi.fn().mockResolvedValue({
    client_tenants: null,
    active_platform_users: null,
    recent_activity: null,
  }),
  fetchWorkspaceStats: vi
    .fn()
    .mockResolvedValue({ members: null, pending_invites: null, recent_activity: null }),
  apiFetch: vi.fn().mockResolvedValue({
    id: "u1",
    email: "test@example.com",
    role: "super_admin",
    is_active: true,
  }),
}));

function renderAt(initial: string) {
  // Post-#57 the Zustand auth store is the single source of truth that AuthGuard
  // reads. `initAuth()` only seeds it once at module-load (when holders.session
  // was still null), so each case seeds the store explicitly from holders.session
  // — the same value the getSession mock returns — to a terminal auth status.
  useAuthStore.setState({
    session: holders.session as Session | null,
    userId: holders.session?.user.id ?? null,
    status: holders.session ? "authenticated" : "unauthenticated",
  });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initial] }),
  });
  render(<RouterProvider router={router} />);
}

const SIDEBAR = '[data-slot="sidebar"]';

const platformOnlyMe: MeResponse = {
  user_id: "u1",
  email: "test@example.com",
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.users.read", "platform.clients.read", "platform.settings.read"],
  tenants: [],
  pending_invite: null,
};

const workspaceOnlyMe: MeResponse = {
  user_id: "u1",
  email: "test@example.com",
  platform: null,
  platform_permissions: [],
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
};

describe("app shell boundary", () => {
  beforeEach(() => {
    holders.session = null;
    holders.me = null;
    // The singleton queryClient persists across tests; clearing avoids
    // stale ['me'] cache feeding into the next case's AuthGuard decision.
    queryClient.clear();
  });

  it("renders the platform sidebar on /platform", async () => {
    holders.session = { access_token: "test", user: { id: "u1", email: "test@example.com" } };
    holders.me = platformOnlyMe;
    renderAt("/platform");
    // The platform index landed: its distinctive empty-state heading is present.
    await screen.findByRole("heading", { name: /more insight is on the way/i }, { timeout: 5000 });
    expect(document.querySelector(SIDEBAR)).not.toBeNull();
    expect(screen.getByText("Clients")).toBeInTheDocument();
  });

  it("renders the workspace sidebar on /workspace/<id>", async () => {
    // Tenant-only user so getDefaultLandingPath returns /workspace/t1 (not
    // /platform) when the auth-guard navigates through /sign-in on its way to
    // the user's default scope.
    holders.session = { access_token: "test", user: { id: "u1", email: "test@example.com" } };
    holders.me = workspaceOnlyMe;
    renderAt("/workspace/t1");
    // The workspace index landed: its distinctive empty-state heading is present.
    await screen.findByRole("heading", { name: /your workspace is ready/i }, { timeout: 5000 });
    // Scope nav assertions to the sidebar — the workspace overview now also
    // renders a "Members" StatCard in <main>, so a document-wide getByText
    // would match multiple elements. The intent is the sidebar nav set.
    const sidebar = document.querySelector(SIDEBAR);
    expect(sidebar).not.toBeNull();
    const nav = within(sidebar as HTMLElement);
    expect(nav.getByText("Members")).toBeInTheDocument();
    expect(nav.getByText("Audit log")).toBeInTheDocument();
    expect(nav.queryByText("Clients")).toBeNull();
  });

  it("does NOT render the sidebar on /sign-in (shell-bleed guard)", async () => {
    // session stays null → AuthGuard lets /sign-in through.
    renderAt("/sign-in");
    expect(
      await screen.findByRole("heading", { name: /welcome back/i }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(document.querySelector(SIDEBAR)).toBeNull();
  });
});
