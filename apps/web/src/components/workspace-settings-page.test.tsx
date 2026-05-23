import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse, TenantContext, WorkspaceSettingsOut } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { ApiError } from "@/lib/api";
import { WorkspaceSettingsPage } from "./workspace-settings-page";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const WID = "wid-1";

const OWNER_TENANT: TenantContext = {
  id: WID,
  slug: "acme",
  name: "Acme",
  role: "owner",
  permissions: ["workspace.settings.read", "workspace.settings.manage"],
};
const READ_ONLY_TENANT: TenantContext = {
  ...OWNER_TENANT,
  permissions: ["workspace.settings.read"],
};
const NO_ACCESS_TENANT: TenantContext = {
  ...OWNER_TENANT,
  permissions: [],
};

const ME_OWNER: MeResponse = {
  user_id: "u-self",
  email: "owner@acme.com",
  platform: null,
  platform_permissions: [],
  tenants: [OWNER_TENANT],
  pending_invite: null,
};
const ME_READ_ONLY: MeResponse = { ...ME_OWNER, tenants: [READ_ONLY_TENANT] };
const ME_NO_ACCESS: MeResponse = { ...ME_OWNER, tenants: [NO_ACCESS_TENANT] };

const SETTINGS: WorkspaceSettingsOut = {
  id: WID,
  slug: "acme",
  name: "Acme",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchWorkspaceSettings: vi.fn(),
    updateWorkspaceSettings: vi.fn(),
  };
});

import * as api from "@/lib/api";
import { toast } from "sonner";

beforeEach(() => {
  vi.clearAllMocks();
});

function renderWith(qc: QueryClient) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({
      initialEntries: [`/workspace/${WID}/settings`],
    }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <WorkspaceSettingsPage workspaceId={WID} />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("<WorkspaceSettingsPage />", () => {
  it("renders <Forbidden /> when me lacks workspace.settings.read", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_NO_ACCESS);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() =>
      expect(screen.getByText(/don't have access|don't have permission/i)).toBeInTheDocument(),
    );
  });

  it("disables Save when caller only has read access", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_READ_ONLY);
    vi.mocked(api.fetchWorkspaceSettings).mockResolvedValue(SETTINGS);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => expect(screen.getByLabelText(/^name$/i)).toHaveValue("Acme"));
    expect(screen.getByLabelText(/^name$/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
  });

  it("renames the workspace, fires the success toast, and invalidates the settings cache", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceSettings).mockResolvedValue(SETTINGS);
    vi.mocked(api.updateWorkspaceSettings).mockResolvedValue({
      ...SETTINGS,
      name: "Acme Corp",
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => expect(screen.getByLabelText(/^name$/i)).toHaveValue("Acme"));
    const input = screen.getByLabelText(/^name$/i);
    await userEvent.clear(input);
    await userEvent.type(input, "Acme Corp");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(api.updateWorkspaceSettings).toHaveBeenCalledWith(WID, {
        name: "Acme Corp",
      });
    });
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("Settings saved");
    });
    await waitFor(() => {
      expect(api.fetchWorkspaceSettings).toHaveBeenCalledTimes(2);
    });
  });

  it("renders an inline error on 422", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceSettings).mockResolvedValue(SETTINGS);
    vi.mocked(api.updateWorkspaceSettings).mockRejectedValue(
      new ApiError(422, { detail: "workspace_name_invalid" }),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => expect(screen.getByLabelText(/^name$/i)).toHaveValue("Acme"));
    const input = screen.getByLabelText(/^name$/i);
    await userEvent.clear(input);
    await userEvent.type(input, "Acme Corp");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(screen.getByText(/workspace name must be 2-200 characters/i)).toBeInTheDocument();
    });
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("keeps Save disabled when name is unchanged (no-op)", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceSettings).mockResolvedValue(SETTINGS);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => expect(screen.getByLabelText(/^name$/i)).toHaveValue("Acme"));
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
  });

  it("disables Save when name is empty", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceSettings).mockResolvedValue(SETTINGS);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => expect(screen.getByLabelText(/^name$/i)).toHaveValue("Acme"));
    const input = screen.getByLabelText(/^name$/i);
    await userEvent.clear(input);
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
  });
});
