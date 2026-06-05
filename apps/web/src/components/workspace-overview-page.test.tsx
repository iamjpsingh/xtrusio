import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse, TenantContext, WorkspaceStats } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { WorkspaceOverviewPage } from "./workspace-overview-page";

const WID = "wid-1";

const OWNER_TENANT: TenantContext = {
  id: WID,
  slug: "acme",
  name: "Acme",
  role: "owner",
  permissions: ["workspace.members.read", "workspace.audit.read"],
};
const ME_OWNER: MeResponse = {
  user_id: "u-self",
  email: "owner@acme.com",
  platform: null,
  platform_permissions: [],
  tenants: [OWNER_TENANT],
  pending_invite: null,
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, fetchMe: vi.fn(), fetchWorkspaceStats: vi.fn() };
});

import * as api from "@/lib/api";
import { ApiError, SessionExpiredError } from "@/lib/api";

const mockedMe = vi.mocked(api.fetchMe);
const mockedStats = vi.mocked(api.fetchWorkspaceStats);

beforeEach(() => {
  vi.clearAllMocks();
  mockedMe.mockResolvedValue(ME_OWNER);
});

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderWith(qc: QueryClient) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [`/workspace/${WID}`] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <WorkspaceOverviewPage workspaceId={WID} />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("<WorkspaceOverviewPage />", () => {
  it("renders all three metric values + the workspace name", async () => {
    const stats: WorkspaceStats = { members: 4, pending_invites: 2, recent_activity: 11 };
    mockedStats.mockResolvedValue(stats);
    renderWith(newClient());
    await waitFor(() => {
      expect(screen.getByText("4")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("11")).toBeInTheDocument();
    });
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.getByText("Pending invites")).toBeInTheDocument();
    expect(screen.getByText("Recent activity")).toBeInTheDocument();
  });

  it("omits Recent activity when its field is null (read_only member)", async () => {
    const stats: WorkspaceStats = { members: 4, pending_invites: 2, recent_activity: null };
    mockedStats.mockResolvedValue(stats);
    renderWith(newClient());
    await waitFor(() => expect(screen.getByText("4")).toBeInTheDocument());
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.getByText("Pending invites")).toBeInTheDocument();
    expect(screen.queryByText("Recent activity")).toBeNull();
  });

  it("shows a loading skeleton in each card while pending", async () => {
    let resolve: (s: WorkspaceStats) => void = () => {};
    mockedStats.mockReturnValue(
      new Promise<WorkspaceStats>((r) => {
        resolve = r;
      }),
    );
    const { container } = renderWith(newClient());
    await waitFor(() => {
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(3);
    });
    resolve({ members: 1, pending_invites: 1, recent_activity: 1 });
    await waitFor(() =>
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(0),
    );
  });

  it("shows a retryable error state on a 5xx failure", async () => {
    mockedStats.mockRejectedValueOnce(new ApiError(500, { detail: "internal_error" }));
    renderWith(newClient());
    await waitFor(() => expect(screen.getByText(/couldn't load metrics/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    mockedStats.mockResolvedValue({ members: 8, pending_invites: 0, recent_activity: 3 });
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(screen.getByText("8")).toBeInTheDocument());
  });

  it("renders the Forbidden surface with NO retry on a 403", async () => {
    mockedStats.mockRejectedValue(new ApiError(403, { detail: "forbidden" }));
    renderWith(newClient());
    await waitFor(() =>
      expect(screen.getByText(/don't have (access|permission)/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/couldn't load metrics/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });

  it("suppresses the error flash on a SessionExpiredError — renders the loader, not ErrorState", async () => {
    mockedStats.mockRejectedValue(new SessionExpiredError());
    const { container } = renderWith(newClient());
    // A sign-out redirect is imminent: show skeletons, never the error surface.
    await waitFor(() =>
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(3),
    );
    expect(screen.queryByText(/couldn't load metrics/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });

  it("suppresses the error flash on a raw 401 — renders the loader, not ErrorState", async () => {
    mockedStats.mockRejectedValue(new ApiError(401, { detail: "expired" }));
    const { container } = renderWith(newClient());
    await waitFor(() =>
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(3),
    );
    expect(screen.queryByText(/couldn't load metrics/i)).toBeNull();
  });
});
