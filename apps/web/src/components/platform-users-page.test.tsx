import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type {
  MeResponse,
  PlatformRoleGrantsPage,
  PlatformUsersPage as PlatformUsersPageBody,
} from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { server } from "@/test/msw/server";
import { installMswServer } from "@/test/msw/install";
import { meSuperAdmin, platformUserAna, platformUserBen } from "@/test/msw/fixtures";
import { PlatformUsersPage } from "./platform-users-page";

// MSW-based (F.2): driven through the genuine `apiFetch` → network path with a
// deterministic mocked session token.
vi.mock("@/lib/session-cache", () => ({
  resolveSession: vi.fn().mockResolvedValue({ access_token: "test-tok" }),
  getCachedSession: vi.fn().mockReturnValue({ access_token: "test-tok" }),
}));

installMswServer();

const API = "http://api.test.invalid";

const ME_READ_ONLY: MeResponse = {
  ...meSuperAdmin,
  platform_permissions: ["platform.users.read"],
};
const ME_NONE: MeResponse = { ...meSuperAdmin, platform_permissions: [] };

function me(value: MeResponse) {
  return http.get(`${API}/api/me`, () => HttpResponse.json(value));
}

function renderWith(qc: QueryClient) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/platform/users"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <PlatformUsersPage />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("<PlatformUsersPage />", () => {
  it("renders <Forbidden /> when me lacks platform.users.read", async () => {
    server.use(me(ME_NONE));
    renderWith(newClient());
    await waitFor(() =>
      expect(screen.getByText(/don't have access|don't have permission/i)).toBeInTheDocument(),
    );
  });

  it("renders the empty state when the list is empty", async () => {
    server.use(
      me(meSuperAdmin),
      http.get(`${API}/api/platform/users`, () =>
        HttpResponse.json<PlatformUsersPageBody>({ items: [], next_cursor: null }),
      ),
    );
    renderWith(newClient());
    await waitFor(() => expect(screen.getByText(/no platform users yet/i)).toBeInTheDocument());
  });

  it("renders rows + Manage roles when caller can manage", async () => {
    server.use(
      me(meSuperAdmin),
      http.get(`${API}/api/platform/users`, () =>
        HttpResponse.json<PlatformUsersPageBody>({
          items: [platformUserAna, platformUserBen],
          next_cursor: null,
        }),
      ),
    );
    renderWith(newClient());
    await waitFor(() => {
      expect(screen.getByText("ana@example.com")).toBeInTheDocument();
      expect(screen.getByText("ben@example.com")).toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: /manage roles/i })).toHaveLength(2);
    });
  });

  it("hides Manage roles when caller lacks platform.users.manage", async () => {
    server.use(
      me(ME_READ_ONLY),
      http.get(`${API}/api/platform/users`, () =>
        HttpResponse.json<PlatformUsersPageBody>({ items: [platformUserAna], next_cursor: null }),
      ),
    );
    renderWith(newClient());
    await waitFor(() => screen.getByText("ana@example.com"));
    expect(screen.queryByRole("button", { name: /manage roles/i })).toBeNull();
  });

  it("opens <GrantManagerDialog> when Manage roles is clicked", async () => {
    server.use(
      me(meSuperAdmin),
      http.get(`${API}/api/platform/users`, () =>
        HttpResponse.json<PlatformUsersPageBody>({ items: [platformUserAna], next_cursor: null }),
      ),
      http.get(`${API}/api/platform/users/:userId/roles`, () =>
        HttpResponse.json<PlatformRoleGrantsPage>({ items: [], next_cursor: null }),
      ),
      http.get(`${API}/api/platform/roles`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    renderWith(newClient());
    await waitFor(() => screen.getByText("ana@example.com"));
    await userEvent.click(screen.getByRole("button", { name: /manage roles/i }));
    await waitFor(() => {
      expect(screen.getByText(/ana@example.com — manage roles/i)).toBeInTheDocument();
    });
  });

  it("accumulates pages when Load more is clicked", async () => {
    // Cursor-paged handler exercises real query-string round-tripping through
    // `apiFetch` (page 1 -> ana + next-1, page 2 -> ben + null).
    server.use(
      me(meSuperAdmin),
      http.get(`${API}/api/platform/users`, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        if (cursor === "next-1") {
          return HttpResponse.json<PlatformUsersPageBody>({
            items: [platformUserBen],
            next_cursor: null,
          });
        }
        return HttpResponse.json<PlatformUsersPageBody>({
          items: [platformUserAna],
          next_cursor: "next-1",
        });
      }),
    );
    renderWith(newClient());
    await waitFor(() => screen.getByText("ana@example.com"));
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => {
      expect(screen.getByText("ben@example.com")).toBeInTheDocument();
    });
  });
});
