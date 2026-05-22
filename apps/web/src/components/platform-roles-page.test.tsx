import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterContextProvider,
  createMemoryHistory,
  createRouter,
} from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse, PermissionsCatalog } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { PlatformRolesPage } from "./platform-roles-page";

const ME_WITH: MeResponse = {
  user_id: "u-1",
  email: "super@xtrusio.com",
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.roles.manage"],
  tenants: [],
  pending_invite: null,
};

const ME_WITHOUT: MeResponse = {
  ...ME_WITH,
  platform_permissions: [],
};

const CATALOG: PermissionsCatalog = {
  items: [
    {
      scope: "platform",
      key: "platform.users.read",
      category: "Platform users",
      description: "View platform users",
    },
  ],
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchPermissionsCatalog: vi.fn(),
    fetchPlatformRoles: vi.fn(),
    postPlatformRole: vi.fn(),
    patchPlatformRole: vi.fn(),
    deletePlatformRole: vi.fn(),
  };
});

import * as api from "@/lib/api";

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

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchPermissionsCatalog).mockResolvedValue(CATALOG);
  vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
});

describe("<PlatformRolesPage />", () => {
  it("renders <Forbidden /> when me lacks platform.roles.manage", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITHOUT);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(
        screen.getByText(/don't have access|don't have permission/i),
      ).toBeInTheDocument();
    });
  });

  it("renders table + Create button when perm is held", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /create role/i }),
      ).toBeInTheDocument();
    });
  });

  it("posts a new role and invalidates the platform-roles cache key", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    vi.mocked(api.postPlatformRole).mockResolvedValue({
      id: "r-new",
      key: "auditor",
      name: "Auditor",
      description: null,
      is_system: false,
      permission_keys: ["platform.users.read"],
      created_at: "2026-05-22T00:00:00Z",
      updated_at: "2026-05-22T00:00:00Z",
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() =>
      screen.getByRole("button", { name: /create role/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /create role/i }),
    );
    await userEvent.type(screen.getByLabelText(/key/i), "auditor");
    await userEvent.type(screen.getByLabelText(/name/i), "Auditor");
    await userEvent.click(
      screen.getByRole("checkbox", { name: /platform.users.read/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(api.postPlatformRole).toHaveBeenCalledWith({
        key: "auditor",
        name: "Auditor",
        description: null,
        permission_keys: ["platform.users.read"],
      });
    });
    // After invalidation, fetchPlatformRoles is re-called.
    await waitFor(() => {
      expect(vi.mocked(api.fetchPlatformRoles)).toHaveBeenCalledTimes(2);
    });
  });
});
