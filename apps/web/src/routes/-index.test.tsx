import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { routeTree } from "@/routeTree.gen";
import type { MeResponse } from "@xtrusio/api-types";
import type { Session } from "@supabase/supabase-js";
import { queryClient } from "@/lib/query-client";
import { useAuthStore } from "@/lib/auth-store";

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
  // The platform index now fetches dashboard stats; this route-landing test
  // only asserts the empty-state heading, so an all-null stats payload (every
  // metric card omitted) is enough to keep the dashboard rendering.
  fetchPlatformStats: vi.fn().mockResolvedValue({
    client_tenants: null,
    active_platform_users: null,
    recent_activity: null,
  }),
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
  // was still null), so seed the store explicitly from holders.session — the
  // same value the getSession mock returns — to a terminal auth status.
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

describe("/ Dashboard route", () => {
  beforeEach(() => {
    holders.session = null;
    holders.me = null;
    queryClient.clear();
  });

  it("redirects an authenticated super_admin from / to /platform and shows the welcome empty state", async () => {
    holders.session = { access_token: "test", user: { id: "u1", email: "test@example.com" } };
    holders.me = {
      user_id: "u1",
      email: "test@example.com",
      platform: { role: "super_admin", is_active: true },
      platform_permissions: [
        "platform.users.read",
        "platform.clients.read",
        "platform.settings.read",
      ],
      tenants: [],
      pending_invite: null,
    };
    renderAt("/");
    // AuthGuard redirects / → /platform; the platform index's distinctive
    // empty-state heading confirms the landing.
    expect(
      await screen.findByRole(
        "heading",
        { name: /more insight is on the way/i },
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
  });
});
