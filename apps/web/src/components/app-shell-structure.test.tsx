import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRouter,
} from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/lib/auth";
import { AppShellLayout } from "@/routes/_app";

// AppShellLayout renders the real shell (AppSidebar + AppTopbar/UserMenu),
// which depend on router context (useRouterState/Link) and AuthProvider
// (useAuth). Mount it under a minimal in-memory router + AuthProvider so the
// structural shell can be asserted in isolation, mirroring the harness used
// by routes/-index.test.tsx.
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

function renderShell() {
  const rootRoute = createRootRoute({
    component: () => <AppShellLayout testChildren={<div data-testid="page" />} />,
  });
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("app shell layout", () => {
  it("renders the sidebar shell around an outlet slot", async () => {
    renderShell();
    expect(await screen.findByTestId("page")).toBeInTheDocument();
    expect(document.querySelector('[data-slot="sidebar"], nav, aside')).not.toBeNull();
  });
});
