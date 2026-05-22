import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { routeTree } from "@/routeTree.gen";
import type { MeResponse } from "@xtrusio/api-types";
import { queryClient } from "@/lib/query-client";

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
    expect(
      await screen.findByRole("heading", { name: /welcome to xtrusio/i }, { timeout: 5000 }),
    ).toBeInTheDocument();
  });
});
