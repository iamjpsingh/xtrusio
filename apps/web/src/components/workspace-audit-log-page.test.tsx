import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterContextProvider,
  createMemoryHistory,
  createRouter,
} from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AuditEventOut,
  MeResponse,
  TenantContext,
} from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { WorkspaceAuditLogPage } from "./workspace-audit-log-page";

const WID = "wid-1";

const OWNER_TENANT: TenantContext = {
  id: WID,
  slug: "acme",
  name: "Acme",
  role: "owner",
  permissions: ["workspace.audit.read"],
};
const EDITOR_TENANT: TenantContext = {
  ...OWNER_TENANT,
  role: "editor",
  permissions: ["workspace.members.read"],
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
  tenants: [EDITOR_TENANT],
};

const EV1: AuditEventOut = {
  id: 1,
  actor_auth_user_id: "u-1",
  actor_email: "owner@acme.com",
  action: "workspace_role.create",
  target_type: "role",
  target_id: "tid-1",
  scope: "workspace",
  workspace_id: WID,
  before: null,
  after: { key: "viewer" },
  created_at: "2026-05-22T10:00:00Z",
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchWorkspaceAuditLog: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => vi.clearAllMocks());

function renderWith(qc: QueryClient) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <WorkspaceAuditLogPage workspaceId={WID} />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("<WorkspaceAuditLogPage />", () => {
  it("renders <Forbidden /> when me lacks workspace.audit.read for this workspace", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_NOT_OWNER);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() =>
      expect(
        screen.getByText(/don't have access|don't have permission/i),
      ).toBeInTheDocument(),
    );
  });

  it("renders the first page scoped to this workspace", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceAuditLog).mockResolvedValue({
      items: [EV1],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("workspace_role.create"));
    expect(api.fetchWorkspaceAuditLog).toHaveBeenCalledWith(WID, undefined);
  });

  it("accumulates pages when Load more is clicked", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceAuditLog)
      .mockResolvedValueOnce({ items: [EV1], next_cursor: "next-1" })
      .mockResolvedValueOnce({
        items: [{ ...EV1, id: 2, action: "workspace_role.delete" }],
        next_cursor: null,
      });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("workspace_role.create"));
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() =>
      expect(screen.getByText("workspace_role.delete")).toBeInTheDocument(),
    );
    expect(api.fetchWorkspaceAuditLog).toHaveBeenLastCalledWith(WID, "next-1");
  });
});
