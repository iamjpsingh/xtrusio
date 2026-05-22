import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { routeTree } from "@/routeTree.gen";
import type { MeResponse } from "@xtrusio/api-types";
import { queryClient } from "@/lib/query-client";

// Each case below sets `session` and `me` via these mutable holders, then we
// reset the supabase + fetchMe mocks in beforeEach. `__root.tsx` already wraps
// the tree with ThemeProvider + QueryClientProvider + AuthProvider — we
// deliberately render the bare RouterProvider here; double-wrapping caused the
// supabase subscription to misfire and the body to come out empty.
const holders = {
  session: null as { access_token: string; user: { id: string; email: string } } | null,
  me: null as MeResponse | null,
};

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
  apiFetch: vi.fn().mockResolvedValue({
    id: "u1",
    email: "test@example.com",
    role: "super_admin",
    is_active: true,
  }),
}));

function renderAt(initial: string) {
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
    await screen.findByRole("heading", { name: /welcome to xtrusio/i }, { timeout: 5000 });
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
    await screen.findByRole("heading", { name: /workspace ready/i }, { timeout: 5000 });
    expect(document.querySelector(SIDEBAR)).not.toBeNull();
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.getByText("Audit log")).toBeInTheDocument();
    expect(screen.queryByText("Clients")).toBeNull();
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
