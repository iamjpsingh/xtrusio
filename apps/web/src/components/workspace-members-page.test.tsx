import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse, TenantContext } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { WorkspaceMembersPage } from "./workspace-members-page";

const WID = "wid-1";

const OWNER_TENANT: TenantContext = {
  id: WID,
  slug: "acme",
  name: "Acme",
  role: "owner",
  permissions: ["workspace.members.read", "workspace.members.invite"],
};

const EDITOR_READ_TENANT: TenantContext = {
  ...OWNER_TENANT,
  role: "editor",
  permissions: ["workspace.members.read"],
};

const EDITOR_NO_ACCESS_TENANT: TenantContext = {
  ...OWNER_TENANT,
  role: "editor",
  permissions: [],
};

const ME_INVITER: MeResponse = {
  user_id: "u-1",
  email: "owner@acme.com",
  platform: null,
  platform_permissions: [],
  tenants: [OWNER_TENANT],
  pending_invite: null,
};

const ME_READ_ONLY: MeResponse = {
  ...ME_INVITER,
  tenants: [EDITOR_READ_TENANT],
};

const ME_NO_ACCESS: MeResponse = {
  ...ME_INVITER,
  tenants: [EDITOR_NO_ACCESS_TENANT],
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchTenantInvites: vi.fn(),
    postTenantInvite: vi.fn(),
    deleteTenantInvite: vi.fn(),
    fetchWorkspaceMembers: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchTenantInvites).mockResolvedValue({ items: [] });
  vi.mocked(api.fetchWorkspaceMembers).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
});

function renderWith(qc: QueryClient) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({
      initialEntries: [`/workspace/${WID}/members`],
    }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <WorkspaceMembersPage workspaceId={WID} />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("<WorkspaceMembersPage />", () => {
  it("renders <Forbidden /> when me lacks workspace.members.read", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_NO_ACCESS);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() =>
      expect(screen.getByText(/don't have access|don't have permission/i)).toBeInTheDocument(),
    );
  });

  it("shows the Members section header (formerly the ships-in-P6d notice)", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_READ_ONLY);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 2, name: /^members$/i })).toBeInTheDocument();
    });
    // The placeholder notice from Slice 3 is gone.
    expect(screen.queryByText(/ships in p6d/i)).toBeNull();
  });

  it("hides the Invite button when me lacks workspace.members.invite", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_READ_ONLY);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByRole("heading", { level: 2, name: /^members$/i }));
    expect(screen.queryByRole("button", { name: /invite user/i })).toBeNull();
  });

  it("shows the Invite button + invites list when me has workspace.members.invite", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_INVITER);
    vi.mocked(api.fetchTenantInvites).mockResolvedValue({
      items: [
        {
          id: "inv-1",
          tenant_id: WID,
          email: "guest@acme.com",
          role: "editor",
          expires_at: "2026-06-22T00:00:00Z",
          accepted_at: null,
          revoked_at: null,
          created_at: "2026-05-22T00:00:00Z",
        },
      ],
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /invite user/i })).toBeInTheDocument();
      expect(screen.getByText("guest@acme.com")).toBeInTheDocument();
    });
  });

  it("revokes an invite and invalidates qk.workspaceInvites(wid)", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_INVITER);
    vi.mocked(api.fetchTenantInvites).mockResolvedValue({
      items: [
        {
          id: "inv-1",
          tenant_id: WID,
          email: "guest@acme.com",
          role: "editor",
          expires_at: "2026-06-22T00:00:00Z",
          accepted_at: null,
          revoked_at: null,
          created_at: "2026-05-22T00:00:00Z",
        },
      ],
    });
    vi.mocked(api.deleteTenantInvite).mockResolvedValue();
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("guest@acme.com"));
    await userEvent.click(screen.getByRole("button", { name: /revoke/i }));
    await waitFor(() => {
      expect(api.deleteTenantInvite).toHaveBeenCalledWith(WID, "inv-1");
    });
    await waitFor(() => {
      expect(vi.mocked(api.fetchTenantInvites)).toHaveBeenCalledTimes(2);
    });
  });
});
