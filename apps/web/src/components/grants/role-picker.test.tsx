import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PlatformRoleOut, WorkspaceRoleOut } from "@xtrusio/api-types";
import { RolePicker } from "./role-picker";

const WID = "wid-1";

const PLATFORM_ROLE_A: PlatformRoleOut = {
  id: "pr-a",
  key: "auditor",
  name: "Auditor",
  description: null,
  is_system: false,
  permission_keys: [],
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};
const PLATFORM_ROLE_B: PlatformRoleOut = {
  ...PLATFORM_ROLE_A,
  id: "pr-b",
  key: "compliance",
  name: "Compliance",
};

const WORKSPACE_ROLE_A: WorkspaceRoleOut = {
  id: "wr-a",
  workspace_id: WID,
  key: "viewer",
  name: "Viewer",
  description: null,
  is_system: false,
  permission_keys: [],
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchPlatformRoles: vi.fn(),
    fetchWorkspaceRoles: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
});

function renderPicker(children: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{children}</QueryClientProvider>);
}

describe("<RolePicker scope='platform' />", () => {
  it("renders empty-state copy when no platform roles exist", async () => {
    vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    renderPicker(<RolePicker scope="platform" value={null} onChange={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/no roles available/i)).toBeInTheDocument();
    });
  });

  it("renders one option per platform role and calls onChange with the role id", async () => {
    vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
      items: [PLATFORM_ROLE_A, PLATFORM_ROLE_B],
      next_cursor: null,
    });
    const onChange = vi.fn();
    renderPicker(<RolePicker scope="platform" value={null} onChange={onChange} />);
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: /role/i })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("combobox", { name: /role/i }));
    await userEvent.click(await screen.findByText(/Auditor \(auditor\)/));
    expect(onChange).toHaveBeenCalledWith("pr-a");
  });
});

describe("<RolePicker scope='workspace' />", () => {
  it("renders workspace roles", async () => {
    vi.mocked(api.fetchWorkspaceRoles).mockResolvedValue({
      items: [WORKSPACE_ROLE_A],
      next_cursor: null,
    });
    renderPicker(
      <RolePicker scope="workspace" workspaceId={WID} value={null} onChange={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: /role/i })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("combobox", { name: /role/i }));
    await waitFor(() => {
      expect(screen.getByText(/Viewer \(viewer\)/)).toBeInTheDocument();
    });
  });
});
