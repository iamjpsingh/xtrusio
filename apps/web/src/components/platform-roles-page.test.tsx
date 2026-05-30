import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type {
  MeResponse,
  PlatformRoleOut,
  PlatformRolesPage as PlatformRolesPageBody,
} from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { server } from "@/test/msw/server";
import { installMswServer } from "@/test/msw/install";
import { meSuperAdmin, permissionsCatalog } from "@/test/msw/fixtures";
import { PlatformRolesPage } from "./platform-roles-page";

// MSW-based (F.2): the page is driven through the genuine `apiFetch` → network
// path. `resolveSession` is mocked for a deterministic bearer token.
vi.mock("@/lib/session-cache", () => ({
  resolveSession: vi.fn().mockResolvedValue({ access_token: "test-tok" }),
  getCachedSession: vi.fn().mockReturnValue({ access_token: "test-tok" }),
}));

installMswServer();

const API = "http://api.test.invalid";

function meWithout(): MeResponse {
  return { ...meSuperAdmin, platform_permissions: [] };
}

function renderWith(qc: QueryClient) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/platform/roles"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <PlatformRolesPage />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("<PlatformRolesPage />", () => {
  it("renders <Forbidden /> when me lacks platform.roles.manage", async () => {
    server.use(http.get(`${API}/api/me`, () => HttpResponse.json(meWithout())));
    renderWith(newClient());
    await waitFor(() => {
      expect(screen.getByText(/don't have access|don't have permission/i)).toBeInTheDocument();
    });
  });

  it("renders table + Create button when perm is held", async () => {
    server.use(
      http.get(`${API}/api/me`, () => HttpResponse.json(meSuperAdmin)),
      http.get(`${API}/api/permissions/catalog`, () => HttpResponse.json(permissionsCatalog)),
      http.get(`${API}/api/platform/roles`, () =>
        HttpResponse.json<PlatformRolesPageBody>({ items: [], next_cursor: null }),
      ),
    );
    renderWith(newClient());
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create role/i })).toBeInTheDocument();
    });
  });

  it("posts a new role and refetches the platform-roles list", async () => {
    let listCalls = 0;
    let postedBody: unknown = null;
    server.use(
      http.get(`${API}/api/me`, () => HttpResponse.json(meSuperAdmin)),
      http.get(`${API}/api/permissions/catalog`, () => HttpResponse.json(permissionsCatalog)),
      http.get(`${API}/api/platform/roles`, () => {
        listCalls += 1;
        return HttpResponse.json<PlatformRolesPageBody>({ items: [], next_cursor: null });
      }),
      http.post(`${API}/api/platform/roles`, async ({ request }) => {
        postedBody = await request.json();
        const created: PlatformRoleOut = {
          id: "r-new",
          key: "auditor",
          name: "Auditor",
          description: null,
          is_system: false,
          permission_keys: ["platform.users.read"],
          created_at: "2026-05-22T00:00:00Z",
          updated_at: "2026-05-22T00:00:00Z",
        };
        return HttpResponse.json<PlatformRoleOut>(created, { status: 201 });
      }),
    );
    renderWith(newClient());
    await waitFor(() => screen.getByRole("button", { name: /create role/i }));
    const callsBeforeCreate = listCalls;
    await userEvent.click(screen.getByRole("button", { name: /create role/i }));
    await userEvent.type(screen.getByLabelText(/key/i), "auditor");
    await userEvent.type(screen.getByLabelText(/name/i), "Auditor");
    await userEvent.click(screen.getByRole("checkbox", { name: /platform.users.read/i }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(postedBody).toEqual({
        key: "auditor",
        name: "Auditor",
        description: null,
        permission_keys: ["platform.users.read"],
      });
    });
    // Cache invalidation re-fetches the list (one extra GET after the POST).
    await waitFor(() => {
      expect(listCalls).toBeGreaterThan(callsBeforeCreate);
    });
  });
});
