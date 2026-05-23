import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse, PlatformUserListItem } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { PlatformUsersPage } from "./platform-users-page";

const ME_FULL: MeResponse = {
  user_id: "u-self",
  email: "super@xtrusio.com",
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.users.read", "platform.users.manage"],
  tenants: [],
  pending_invite: null,
};
const ME_READ_ONLY: MeResponse = {
  ...ME_FULL,
  platform_permissions: ["platform.users.read"],
};
const ME_NONE: MeResponse = { ...ME_FULL, platform_permissions: [] };

const USER_A: PlatformUserListItem = {
  id: "u-a",
  email: "ana@xtrusio.com",
  role: "admin",
  is_active: true,
  created_at: "2026-05-01T00:00:00Z",
  last_sign_in_at: "2026-05-20T08:00:00Z",
  granted_role_count: 2,
};
const USER_B: PlatformUserListItem = {
  ...USER_A,
  id: "u-b",
  email: "ben@xtrusio.com",
  role: "editor",
  is_active: false,
  last_sign_in_at: null,
  granted_role_count: 0,
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchPlatformUsers: vi.fn(),
    fetchPlatformRoleGrants: vi.fn(),
    fetchPlatformRoles: vi.fn(),
    postPlatformRoleGrant: vi.fn(),
    deletePlatformRoleGrant: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
});

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

describe("<PlatformUsersPage />", () => {
  it("renders <Forbidden /> when me lacks platform.users.read", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_NONE);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() =>
      expect(screen.getByText(/don't have access|don't have permission/i)).toBeInTheDocument(),
    );
  });

  it("renders the empty state when the list is empty", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_FULL);
    vi.mocked(api.fetchPlatformUsers).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => expect(screen.getByText(/no platform users yet/i)).toBeInTheDocument());
  });

  it("renders rows + Manage roles when caller can manage", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_FULL);
    vi.mocked(api.fetchPlatformUsers).mockResolvedValue({
      items: [USER_A, USER_B],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(screen.getByText("ana@xtrusio.com")).toBeInTheDocument();
      expect(screen.getByText("ben@xtrusio.com")).toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: /manage roles/i })).toHaveLength(2);
    });
  });

  it("hides Manage roles when caller lacks platform.users.manage", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_READ_ONLY);
    vi.mocked(api.fetchPlatformUsers).mockResolvedValue({
      items: [USER_A],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("ana@xtrusio.com"));
    expect(screen.queryByRole("button", { name: /manage roles/i })).toBeNull();
  });

  it("opens <GrantManagerDialog> when Manage roles is clicked", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_FULL);
    vi.mocked(api.fetchPlatformUsers).mockResolvedValue({
      items: [USER_A],
      next_cursor: null,
    });
    vi.mocked(api.fetchPlatformRoleGrants).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("ana@xtrusio.com"));
    await userEvent.click(screen.getByRole("button", { name: /manage roles/i }));
    await waitFor(() => {
      expect(screen.getByText(/ana@xtrusio.com — manage roles/i)).toBeInTheDocument();
    });
  });

  it("accumulates pages when Load more is clicked", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_FULL);
    vi.mocked(api.fetchPlatformUsers)
      .mockResolvedValueOnce({ items: [USER_A], next_cursor: "next-1" })
      .mockResolvedValueOnce({ items: [USER_B], next_cursor: null });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("ana@xtrusio.com"));
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => {
      expect(screen.getByText("ben@xtrusio.com")).toBeInTheDocument();
    });
    expect(api.fetchPlatformUsers).toHaveBeenCalledTimes(2);
    expect(api.fetchPlatformUsers).toHaveBeenLastCalledWith("next-1");
  });
});
