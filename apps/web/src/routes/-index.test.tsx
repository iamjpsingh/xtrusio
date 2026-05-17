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
    tenants: [],
    pending_invite: null,
  }),
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

describe("/ Dashboard route", () => {
  it("renders the welcome empty state when authenticated", async () => {
    renderAt("/");
    expect(
      await screen.findByRole("heading", { name: /welcome to xtrusio/i }, { timeout: 3000 }),
    ).toBeInTheDocument();
  });
});
