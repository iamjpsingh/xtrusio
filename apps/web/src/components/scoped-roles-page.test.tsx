import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PermissionsCatalog } from "@xtrusio/api-types";
import { ScopedRolesPage } from "./scoped-roles-page";

const CATALOG: PermissionsCatalog = {
  items: [
    {
      scope: "platform",
      key: "platform.users.read",
      category: "Platform users",
      description: "View platform users",
    },
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
    fetchPermissionsCatalog: vi.fn(),
    fetchPlatformRoles: vi.fn(),
    fetchWorkspaceRoles: vi.fn(),
    postPlatformRole: vi.fn(),
    postWorkspaceRole: vi.fn(),
    patchPlatformRole: vi.fn(),
    patchWorkspaceRole: vi.fn(),
    deletePlatformRole: vi.fn(),
    deleteWorkspaceRole: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchPermissionsCatalog).mockResolvedValue(CATALOG);
  vi.mocked(api.fetchPlatformRoles).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(api.fetchWorkspaceRoles).mockResolvedValue({ items: [], next_cursor: null });
});

function renderScoped(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("<ScopedRolesPage />", () => {
  it("renders the platform copy + Create button and lists platform roles", async () => {
    renderScoped(<ScopedRolesPage scope="platform" />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /platform roles/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /create role/i })).toBeInTheDocument();
    });
    expect(api.fetchPlatformRoles).toHaveBeenCalled();
    expect(api.fetchWorkspaceRoles).not.toHaveBeenCalled();
  });

  it("renders the workspace copy and routes mutations to the workspace API", async () => {
    vi.mocked(api.postWorkspaceRole).mockResolvedValue({
      id: "r-new",
      workspace_id: "wid-1",
      key: "viewer",
      name: "Viewer",
      description: null,
      is_system: false,
      permission_keys: ["workspace.members.read"],
      created_at: "2026-05-22T00:00:00Z",
      updated_at: "2026-05-22T00:00:00Z",
    });
    renderScoped(<ScopedRolesPage scope="workspace" workspaceId="wid-1" />);
    await waitFor(() => screen.getByRole("button", { name: /create role/i }));
    expect(screen.getByRole("heading", { name: /workspace roles/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /create role/i }));
    await userEvent.type(screen.getByLabelText(/key/i), "viewer");
    await userEvent.type(screen.getByLabelText(/name/i), "Viewer");
    await userEvent.click(screen.getByRole("checkbox", { name: /workspace.members.read/i }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(api.postWorkspaceRole).toHaveBeenCalledWith("wid-1", {
        key: "viewer",
        name: "Viewer",
        description: null,
        permission_keys: ["workspace.members.read"],
      });
    });
    // After invalidation the workspace list re-fetches.
    await waitFor(() => expect(vi.mocked(api.fetchWorkspaceRoles)).toHaveBeenCalledTimes(2));
    expect(api.fetchPlatformRoles).not.toHaveBeenCalled();
  });
});
