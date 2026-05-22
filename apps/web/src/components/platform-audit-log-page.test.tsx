import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterContextProvider,
  createMemoryHistory,
  createRouter,
} from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditEventOut, MeResponse } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { PlatformAuditLogPage } from "./platform-audit-log-page";

const ME_WITH: MeResponse = {
  user_id: "u-1",
  email: "super@xtrusio.com",
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.audit.read"],
  tenants: [],
  pending_invite: null,
};
const ME_WITHOUT: MeResponse = { ...ME_WITH, platform_permissions: [] };

const EV1: AuditEventOut = {
  id: 1,
  actor_auth_user_id: "u-1",
  actor_email: "ana@acme.com",
  action: "platform_role.create",
  target_type: "role",
  target_id: "tid-1",
  scope: "platform",
  workspace_id: null,
  before: null,
  after: { key: "dispatcher" },
  created_at: "2026-05-22T10:00:00Z",
};
const EV2: AuditEventOut = { ...EV1, id: 2, action: "platform_role.update" };

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchPlatformAuditLog: vi.fn(),
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
        <PlatformAuditLogPage />
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("<PlatformAuditLogPage />", () => {
  it("renders <Forbidden /> when me lacks platform.audit.read", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITHOUT);
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

  it("renders the first page of events", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    vi.mocked(api.fetchPlatformAuditLog).mockResolvedValue({
      items: [EV1, EV2],
      next_cursor: "next-1",
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(screen.getByText("platform_role.create")).toBeInTheDocument();
      expect(screen.getByText("platform_role.update")).toBeInTheDocument();
    });
  });

  it("accumulates pages when Load more is clicked", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    vi.mocked(api.fetchPlatformAuditLog)
      .mockResolvedValueOnce({ items: [EV1], next_cursor: "next-1" })
      .mockResolvedValueOnce({
        items: [{ ...EV2, action: "platform_role.delete" }],
        next_cursor: null,
      });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("platform_role.create"));
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => {
      expect(screen.getByText("platform_role.create")).toBeInTheDocument();
      expect(screen.getByText("platform_role.delete")).toBeInTheDocument();
    });
    expect(api.fetchPlatformAuditLog).toHaveBeenCalledTimes(2);
    expect(api.fetchPlatformAuditLog).toHaveBeenLastCalledWith("next-1");
  });

  it("opens the drawer with the clicked event", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    vi.mocked(api.fetchPlatformAuditLog).mockResolvedValue({
      items: [EV1],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("platform_role.create"));
    await userEvent.click(screen.getByText("platform_role.create"));
    await waitFor(() =>
      expect(screen.getByText(/"key": "dispatcher"/)).toBeInTheDocument(),
    );
  });
});
