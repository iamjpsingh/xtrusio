import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { TenantsPage } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { server } from "@/test/msw/server";
import { installMswServer } from "@/test/msw/install";
import { tenantAcme, tenantGlobex } from "@/test/msw/fixtures";
import { ClientsPage } from "./clients-page";

// MSW-based: driven through the genuine `apiFetch` → network path with a
// deterministic mocked session token (mirrors the platform-users-page test).
vi.mock("@/lib/session-cache", () => ({
  resolveSession: vi.fn().mockResolvedValue({ access_token: "test-tok" }),
  getCachedSession: vi.fn().mockReturnValue({ access_token: "test-tok" }),
}));

installMswServer();

const API = "http://api.test.invalid";

function renderPage(qc: QueryClient) {
  // A real router context is needed so the row <Link> can resolve hrefs.
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/platform/clients"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <ClientsPage />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("<ClientsPage /> (platform Clients page)", () => {
  it("renders a row per client from the TenantsPage envelope's items", async () => {
    // Regression for `tenants-list-shape-mismatch`: the page must read `items`
    // from the cursor-paginated envelope. The old code typed the response as
    // `Tenant[]` and called `.map`/`.length` on the envelope object, so it
    // never rendered any rows (and threw on `.map`).
    server.use(
      http.get(`${API}/api/tenants`, () =>
        HttpResponse.json<TenantsPage>({
          items: [tenantAcme, tenantGlobex],
          next_cursor: null,
        }),
      ),
    );
    renderPage(newClient());
    await waitFor(() => {
      expect(screen.getByText("Acme Corp")).toBeInTheDocument();
      expect(screen.getByText("Globex")).toBeInTheDocument();
    });
    expect(screen.getByText("acme-corp")).toBeInTheDocument();
  });

  it("links each client row to its per-client detail route", async () => {
    server.use(
      http.get(`${API}/api/tenants`, () =>
        HttpResponse.json<TenantsPage>({ items: [tenantAcme], next_cursor: null }),
      ),
    );
    renderPage(newClient());
    const link = await screen.findByRole("link", { name: "Acme Corp" });
    expect(link).toHaveAttribute("href", "/platform/clients/acme-corp/users");
  });

  it("renders the empty state when items is empty", async () => {
    server.use(
      http.get(`${API}/api/tenants`, () =>
        HttpResponse.json<TenantsPage>({ items: [], next_cursor: null }),
      ),
    );
    renderPage(newClient());
    await waitFor(() => expect(screen.getByText(/no client tenants yet/i)).toBeInTheDocument());
  });

  it("renders an error state and can retry", async () => {
    server.use(
      http.get(`${API}/api/tenants`, () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    renderPage(newClient());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument(),
    );
  });

  it("accumulates pages when Load more is clicked", async () => {
    server.use(
      http.get(`${API}/api/tenants`, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        if (cursor === "next-1") {
          return HttpResponse.json<TenantsPage>({ items: [tenantGlobex], next_cursor: null });
        }
        return HttpResponse.json<TenantsPage>({ items: [tenantAcme], next_cursor: "next-1" });
      }),
    );
    renderPage(newClient());
    await waitFor(() => screen.getByText("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => expect(screen.getByText("Globex")).toBeInTheDocument());
  });
});
