import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse, TenantContext, WorkspaceMemberListItem } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { WorkspaceMembersListPage } from "./workspace-members-list-page";

const WID = "wid-1";

const OWNER_TENANT: TenantContext = {
  id: WID,
  slug: "acme",
  name: "Acme",
  role: "owner",
  permissions: ["workspace.members.read", "workspace.members.manage"],
};
const READ_ONLY_TENANT: TenantContext = {
  ...OWNER_TENANT,
  role: "editor",
  permissions: ["workspace.members.read"],
};
const NO_ACCESS_TENANT: TenantContext = {
  ...OWNER_TENANT,
  role: "editor",
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

const MEMBER_A: WorkspaceMemberListItem = {
  user_id: "u-a",
  email: "alice@acme.com",
  role: "admin",
  joined_at: "2026-05-01T00:00:00Z",
  granted_role_count: 1,
};
const MEMBER_HARD_DELETED: WorkspaceMemberListItem = {
  ...MEMBER_A,
  user_id: "u-b",
  email: null,
  role: "editor",
  granted_role_count: 0,
};
// An owner member (Remove must be hidden — owners are protected).
const MEMBER_OWNER: WorkspaceMemberListItem = {
  ...MEMBER_A,
  user_id: "u-owner",
  email: "boss@acme.com",
  role: "owner",
};
// The current user's own row (Remove must be hidden — can't remove yourself).
const MEMBER_SELF: WorkspaceMemberListItem = {
  ...MEMBER_A,
  user_id: "u-self",
  email: "owner@acme.com",
  role: "admin",
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchWorkspaceMembers: vi.fn(),
    fetchWorkspaceRoleGrants: vi.fn(),
    fetchWorkspaceRoles: vi.fn(),
    postWorkspaceRoleGrant: vi.fn(),
    deleteWorkspaceRoleGrant: vi.fn(),
    deleteWorkspaceMember: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
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
        <WorkspaceMembersListPage workspaceId={WID} />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("<WorkspaceMembersListPage />", () => {
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

  it("renders the empty state when no members", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceMembers).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => expect(screen.getByText(/no members yet/i)).toBeInTheDocument());
  });

  it("renders rows + Manage roles when caller can manage", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceMembers).mockResolvedValue({
      items: [MEMBER_A, MEMBER_HARD_DELETED],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(screen.getByText("alice@acme.com")).toBeInTheDocument();
      // Hard-deleted auth.users row surfaces as an em-dash.
      expect(screen.getAllByText("—")).not.toHaveLength(0);
      expect(screen.getAllByRole("button", { name: /manage roles/i })).toHaveLength(2);
    });
  });

  it("hides Manage roles when caller lacks workspace.members.manage", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_READ_ONLY);
    vi.mocked(api.fetchWorkspaceMembers).mockResolvedValue({
      items: [MEMBER_A],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("alice@acme.com"));
    expect(screen.queryByRole("button", { name: /manage roles/i })).toBeNull();
  });

  it("opens <GrantManagerDialog scope='workspace'> when Manage roles is clicked", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceMembers).mockResolvedValue({
      items: [MEMBER_A],
      next_cursor: null,
    });
    vi.mocked(api.fetchWorkspaceRoleGrants).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    vi.mocked(api.fetchWorkspaceRoles).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("alice@acme.com"));
    await userEvent.click(screen.getByRole("button", { name: /manage roles/i }));
    await waitFor(() => {
      expect(screen.getByText(/alice@acme.com — manage roles/i)).toBeInTheDocument();
    });
  });

  it("accumulates pages when Load more is clicked", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceMembers)
      .mockResolvedValueOnce({ items: [MEMBER_A], next_cursor: "next-1" })
      .mockResolvedValueOnce({
        items: [MEMBER_HARD_DELETED],
        next_cursor: null,
      });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("alice@acme.com"));
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => {
      // Both rows should now be visible.
      expect(screen.getAllByText(/manage roles|alice@acme.com/i).length).toBeGreaterThan(1);
    });
    expect(api.fetchWorkspaceMembers).toHaveBeenCalledTimes(2);
    expect(api.fetchWorkspaceMembers).toHaveBeenLastCalledWith(WID, "next-1");
  });

  it("shows Remove for a non-owner, non-self member when caller can manage", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceMembers).mockResolvedValue({
      items: [MEMBER_A],
      next_cursor: null,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWith(qc);
    await waitFor(() => screen.getByText("alice@acme.com"));
    expect(screen.getByRole("button", { name: /^remove$/i })).toBeInTheDocument();
  });

  it("hides Remove for an owner member and for the current user's own row", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceMembers).mockResolvedValue({
      items: [MEMBER_OWNER, MEMBER_SELF],
      next_cursor: null,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWith(qc);
    await waitFor(() => screen.getByText("boss@acme.com"));
    // Neither the owner row nor the self row exposes a Remove button.
    expect(screen.queryByRole("button", { name: /^remove$/i })).toBeNull();
    // But Manage roles is still present for both (manage gate unchanged).
    expect(screen.getAllByRole("button", { name: /manage roles/i })).toHaveLength(2);
  });

  it("removes a member after confirming the dialog", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceMembers).mockResolvedValue({
      items: [MEMBER_A],
      next_cursor: null,
    });
    vi.mocked(api.deleteWorkspaceMember).mockResolvedValue(undefined);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWith(qc);
    await waitFor(() => screen.getByText("alice@acme.com"));
    await userEvent.click(screen.getByRole("button", { name: /^remove$/i }));
    // Confirm dialog opens; click the destructive Remove button inside it.
    await waitFor(() => screen.getByText(/remove member — alice@acme.com/i));
    const confirm = screen
      .getAllByRole("button", { name: /^remove$/i })
      .find((b) => b.textContent === "Remove" && b.closest('[role="dialog"]'));
    await userEvent.click(confirm!);
    await waitFor(() => {
      expect(api.deleteWorkspaceMember).toHaveBeenCalledWith(WID, "u-a");
    });
  });
});
