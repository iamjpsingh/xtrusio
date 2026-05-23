import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  PlatformRoleGrantOut,
  PlatformRoleOut,
  WorkspaceRoleGrantOut,
  WorkspaceRoleOut,
} from "@xtrusio/api-types";
import { ApiError } from "@/lib/api";
import { GrantManagerDialog } from "./grant-manager-dialog";

const WID = "wid-1";
const UID = "u-1";

const PLATFORM_ROLE: PlatformRoleOut = {
  id: "pr-a",
  key: "auditor",
  name: "Auditor",
  description: null,
  is_system: false,
  permission_keys: [],
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};
const WORKSPACE_ROLE: WorkspaceRoleOut = {
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
const PLATFORM_GRANT_X: PlatformRoleGrantOut = {
  id: "pg-x",
  auth_user_id: UID,
  role_id: "pr-existing",
  role_key: "compliance",
  granted_at: "2026-05-22T00:00:00Z",
  granted_by: null,
};
const WORKSPACE_GRANT_X: WorkspaceRoleGrantOut = {
  id: "wg-x",
  auth_user_id: UID,
  workspace_id: WID,
  role_id: "wr-existing",
  role_key: "billing",
  granted_at: "2026-05-22T00:00:00Z",
  granted_by: null,
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchPlatformRoles: vi.fn(),
    fetchWorkspaceRoles: vi.fn(),
    fetchPlatformRoleGrants: vi.fn(),
    fetchWorkspaceRoleGrants: vi.fn(),
    postPlatformRoleGrant: vi.fn(),
    postWorkspaceRoleGrant: vi.fn(),
    deletePlatformRoleGrant: vi.fn(),
    deleteWorkspaceRoleGrant: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
});

function renderWith(children: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{children}</QueryClientProvider>);
}

describe("<GrantManagerDialog scope='platform' />", () => {
  it("lists existing platform grants for the user", async () => {
    vi.mocked(api.fetchPlatformRoleGrants).mockResolvedValue({
      items: [PLATFORM_GRANT_X],
      next_cursor: null,
    });
    vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
      items: [PLATFORM_ROLE],
      next_cursor: null,
    });
    renderWith(
      <GrantManagerDialog
        scope="platform"
        open
        userId={UID}
        email="ana@xtrusio.com"
        onOpenChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText("compliance")).toBeInTheDocument();
    });
  });

  it("grants a new platform role and invalidates the parent list cache", async () => {
    vi.mocked(api.fetchPlatformRoleGrants).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
      items: [PLATFORM_ROLE],
      next_cursor: null,
    });
    vi.mocked(api.postPlatformRoleGrant).mockResolvedValue({
      ...PLATFORM_GRANT_X,
      role_id: PLATFORM_ROLE.id,
      role_key: PLATFORM_ROLE.key,
    });
    renderWith(
      <GrantManagerDialog
        scope="platform"
        open
        userId={UID}
        email="ana@xtrusio.com"
        onOpenChange={() => {}}
      />,
    );
    await waitFor(() => screen.getByRole("combobox", { name: /role/i }));
    await userEvent.click(screen.getByRole("combobox", { name: /role/i }));
    await userEvent.click(await screen.findByText(/Auditor \(auditor\)/));
    await userEvent.click(screen.getByRole("button", { name: /^grant$/i }));
    await waitFor(() => {
      expect(api.postPlatformRoleGrant).toHaveBeenCalledWith(UID, PLATFORM_ROLE.id);
    });
    // Both the grants list and the parent platform-users list should be refetched.
    await waitFor(() => {
      expect(api.fetchPlatformRoleGrants).toHaveBeenCalledTimes(2);
    });
  });

  it("revokes an existing platform grant", async () => {
    vi.mocked(api.fetchPlatformRoleGrants).mockResolvedValue({
      items: [PLATFORM_GRANT_X],
      next_cursor: null,
    });
    vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    vi.mocked(api.deletePlatformRoleGrant).mockResolvedValue();
    renderWith(
      <GrantManagerDialog
        scope="platform"
        open
        userId={UID}
        email="ana@xtrusio.com"
        onOpenChange={() => {}}
      />,
    );
    await waitFor(() => screen.getByText("compliance"));
    await userEvent.click(screen.getByRole("button", { name: /revoke compliance/i }));
    await waitFor(() => {
      expect(api.deletePlatformRoleGrant).toHaveBeenCalledWith(UID, PLATFORM_GRANT_X.id);
    });
  });

  it("renders the single-super-admin error inline when grant returns 409", async () => {
    vi.mocked(api.fetchPlatformRoleGrants).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
      items: [PLATFORM_ROLE],
      next_cursor: null,
    });
    vi.mocked(api.postPlatformRoleGrant).mockRejectedValue(
      new ApiError(409, { detail: "single_super_admin_invariant" }),
    );
    renderWith(
      <GrantManagerDialog
        scope="platform"
        open
        userId={UID}
        email="ana@xtrusio.com"
        onOpenChange={() => {}}
      />,
    );
    await waitFor(() => screen.getByRole("combobox", { name: /role/i }));
    await userEvent.click(screen.getByRole("combobox", { name: /role/i }));
    await userEvent.click(await screen.findByText(/Auditor \(auditor\)/));
    await userEvent.click(screen.getByRole("button", { name: /^grant$/i }));
    await waitFor(() => {
      expect(screen.getByText(/can't remove the last super admin/i)).toBeInTheDocument();
    });
  });

  it("renders the privilege-escalation error inline when grant returns 403", async () => {
    vi.mocked(api.fetchPlatformRoleGrants).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
      items: [PLATFORM_ROLE],
      next_cursor: null,
    });
    vi.mocked(api.postPlatformRoleGrant).mockRejectedValue(
      new ApiError(403, {
        detail: "privilege_escalation: platform.users.manage",
      }),
    );
    renderWith(
      <GrantManagerDialog
        scope="platform"
        open
        userId={UID}
        email="ana@xtrusio.com"
        onOpenChange={() => {}}
      />,
    );
    await waitFor(() => screen.getByRole("combobox", { name: /role/i }));
    await userEvent.click(screen.getByRole("combobox", { name: /role/i }));
    await userEvent.click(await screen.findByText(/Auditor \(auditor\)/));
    await userEvent.click(screen.getByRole("button", { name: /^grant$/i }));
    await waitFor(() => {
      expect(
        screen.getByText(/can't grant a role with a permission you lack/i),
      ).toBeInTheDocument();
    });
  });
});

describe("<GrantManagerDialog scope='workspace' />", () => {
  it("lists existing workspace grants for the member", async () => {
    vi.mocked(api.fetchWorkspaceRoleGrants).mockResolvedValue({
      items: [WORKSPACE_GRANT_X],
      next_cursor: null,
    });
    vi.mocked(api.fetchWorkspaceRoles).mockResolvedValue({
      items: [WORKSPACE_ROLE],
      next_cursor: null,
    });
    renderWith(
      <GrantManagerDialog
        scope="workspace"
        open
        workspaceId={WID}
        userId={UID}
        email="member@acme.com"
        onOpenChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText("billing")).toBeInTheDocument();
    });
  });

  it("revokes an existing workspace grant", async () => {
    vi.mocked(api.fetchWorkspaceRoleGrants).mockResolvedValue({
      items: [WORKSPACE_GRANT_X],
      next_cursor: null,
    });
    vi.mocked(api.fetchWorkspaceRoles).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    vi.mocked(api.deleteWorkspaceRoleGrant).mockResolvedValue();
    renderWith(
      <GrantManagerDialog
        scope="workspace"
        open
        workspaceId={WID}
        userId={UID}
        email="member@acme.com"
        onOpenChange={() => {}}
      />,
    );
    await waitFor(() => screen.getByText("billing"));
    await userEvent.click(screen.getByRole("button", { name: /revoke billing/i }));
    await waitFor(() => {
      expect(api.deleteWorkspaceRoleGrant).toHaveBeenCalledWith(WID, UID, WORKSPACE_GRANT_X.id);
    });
  });

  it("renders the owner-floor error inline when revoke returns 409", async () => {
    vi.mocked(api.fetchWorkspaceRoleGrants).mockResolvedValue({
      items: [WORKSPACE_GRANT_X],
      next_cursor: null,
    });
    vi.mocked(api.fetchWorkspaceRoles).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    vi.mocked(api.deleteWorkspaceRoleGrant).mockRejectedValue(
      new ApiError(409, { detail: "owner_floor" }),
    );
    renderWith(
      <GrantManagerDialog
        scope="workspace"
        open
        workspaceId={WID}
        userId={UID}
        email="member@acme.com"
        onOpenChange={() => {}}
      />,
    );
    await waitFor(() => screen.getByText("billing"));
    await userEvent.click(screen.getByRole("button", { name: /revoke billing/i }));
    await waitFor(() => {
      expect(screen.getByText(/can't revoke the last workspace owner/i)).toBeInTheDocument();
    });
  });
});
