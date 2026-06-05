import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse, PlatformStats } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { PlatformDashboardPage } from "./platform-dashboard-page";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, fetchPlatformStats: vi.fn(), fetchMe: vi.fn() };
});

import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";

const mockedFetch = vi.mocked(api.fetchPlatformStats);
const mockedMe = vi.mocked(api.fetchMe);

const ME: MeResponse = {
  user_id: "u-self",
  email: "admin@example.com",
  platform: { role: "admin", is_active: true },
  platform_permissions: [],
  tenants: [],
  pending_invite: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockedMe.mockResolvedValue(ME);
});

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderWith(qc: QueryClient) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/platform"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <PlatformDashboardPage />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("<PlatformDashboardPage />", () => {
  it("renders all three metric values from the response", async () => {
    const stats: PlatformStats = {
      client_tenants: 12,
      active_platform_users: 7,
      recent_activity: 34,
    };
    mockedFetch.mockResolvedValue(stats);
    renderWith(newClient());
    await waitFor(() => {
      expect(screen.getByText("12")).toBeInTheDocument();
      expect(screen.getByText("7")).toBeInTheDocument();
      expect(screen.getByText("34")).toBeInTheDocument();
    });
    expect(screen.getByText("Client tenants")).toBeInTheDocument();
    expect(screen.getByText("Platform users")).toBeInTheDocument();
    expect(screen.getByText("Recent activity")).toBeInTheDocument();
  });

  it("omits a card when its field is null (unauthorized metric)", async () => {
    const stats: PlatformStats = {
      client_tenants: null,
      active_platform_users: 7,
      recent_activity: null,
    };
    mockedFetch.mockResolvedValue(stats);
    renderWith(newClient());
    await waitFor(() => expect(screen.getByText("7")).toBeInTheDocument());
    expect(screen.queryByText("Client tenants")).toBeNull();
    expect(screen.queryByText("Recent activity")).toBeNull();
    expect(screen.getByText("Platform users")).toBeInTheDocument();
  });

  it("shows a loading skeleton in each card while pending", async () => {
    let resolve: (s: PlatformStats) => void = () => {};
    mockedFetch.mockReturnValue(
      new Promise<PlatformStats>((r) => {
        resolve = r;
      }),
    );
    const { container } = renderWith(newClient());
    // All three placeholder cards render with a skeleton while in flight.
    await waitFor(() => {
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(3);
    });
    resolve({ client_tenants: 1, active_platform_users: 1, recent_activity: 1 });
    await waitFor(() =>
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(0),
    );
  });

  it("shows a retryable error state on a 5xx failure", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError(503, { detail: "service_unavailable" }));
    renderWith(newClient());
    await waitFor(() => expect(screen.getByText(/couldn't load metrics/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    const stats: PlatformStats = {
      client_tenants: 5,
      active_platform_users: 2,
      recent_activity: 9,
    };
    mockedFetch.mockResolvedValue(stats);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(screen.getByText("5")).toBeInTheDocument());
  });

  it("renders the Forbidden surface with NO retry on a 403", async () => {
    mockedFetch.mockRejectedValue(new ApiError(403, { detail: "forbidden" }));
    renderWith(newClient());
    await waitFor(() =>
      expect(screen.getByText(/don't have (access|permission)/i)).toBeInTheDocument(),
    );
    // The retryable "Couldn't load metrics" / "Try again" must NOT appear.
    expect(screen.queryByText(/couldn't load metrics/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });
});
