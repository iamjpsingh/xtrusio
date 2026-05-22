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
import { WorkspaceRolesPage } from "./workspace-roles-page";

const WID = "wid-1";

const OWNER_TENANT = {
  id: WID,
  slug: "acme",
  name: "Acme",
  role: "owner" as const,
  permissions: ["workspace.roles.manage"],
};

const ME_OWNER: MeResponse = {
  user_id: "u-1",
  email: "owner@acme.com",
  platform: null,
  platform_permissions: [],
  tenants: [OWNER_TENANT],
  pending_invite: null,
};

const ME_NOT_OWNER: MeResponse = {
  ...ME_OWNER,
  tenants: [
    {
      ...OWNER_TENANT,
      role: "editor",
      permissions: ["workspace.members.read"],
    },
  ],
};

const CATALOG: PermissionsCatalog = {
  items: [
    {
      scope: "workspace",
      key: "workspace.members.read",
      category: "Members",
      description: "View workspace members",
    },
  ],
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchPermissionsCatalog: vi.fn(),
    fetchWorkspaceRoles: vi.fn(),
    postWorkspaceRole: vi.fn(),
    patchWorkspaceRole: vi.fn(),
    deleteWorkspaceRole: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchPermissionsCatalog).mockResolvedValue(CATALOG);
  vi.mocked(api.fetchWorkspaceRoles).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
});

function renderWith(qc: QueryClient) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({
      initialEntries: [`/workspace/${WID}/roles`],
    }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <WorkspaceRolesPage workspaceId={WID} />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("<WorkspaceRolesPage />", () => {
  it("renders <Forbidden /> when me lacks workspace.roles.manage for this workspace", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_NOT_OWNER);
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

  it("renders table + Create button when perm is held for this workspace", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
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

  it("posts a new role scoped to this workspace and invalidates the workspace-scoped cache key", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.postWorkspaceRole).mockResolvedValue({
      id: "r-new",
      workspace_id: WID,
      key: "viewer",
      name: "Viewer",
      description: null,
      is_system: false,
      permission_keys: ["workspace.members.read"],
      created_at: "2026-05-22T00:00:00Z",
      updated_at: "2026-05-22T00:00:00Z",
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByRole("button", { name: /create role/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /create role/i }),
    );
    await userEvent.type(screen.getByLabelText(/key/i), "viewer");
    await userEvent.type(screen.getByLabelText(/name/i), "Viewer");
    await userEvent.click(
      screen.getByRole("checkbox", { name: /workspace.members.read/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(api.postWorkspaceRole).toHaveBeenCalledWith(WID, {
        key: "viewer",
        name: "Viewer",
        description: null,
        permission_keys: ["workspace.members.read"],
      });
    });
    await waitFor(() => {
      expect(vi.mocked(api.fetchWorkspaceRoles)).toHaveBeenCalledTimes(2);
    });
  });
});
