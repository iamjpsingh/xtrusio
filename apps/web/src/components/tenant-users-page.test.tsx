import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { MeResponse, PlatformClientDetail, TenantContext } from "@xtrusio/api-types";
import { TenantUsersPage } from "./tenant-users-page";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  fetchPlatformClient: vi.fn(),
  fetchTenantInvites: vi.fn(),
  postTenantInvite: vi.fn(),
  deleteTenantInvite: vi.fn(),
  fetchMe: vi.fn(),
}));
vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ slug: "acme" }),
}));

import { fetchMe, fetchPlatformClient, fetchTenantInvites, postTenantInvite } from "@/lib/api";

const OWNER_TENANT: TenantContext = {
  id: "t-1",
  slug: "acme",
  name: "Acme",
  role: "owner",
  permissions: ["workspace.members.read", "workspace.members.invite"],
};

const EDITOR_TENANT: TenantContext = {
  ...OWNER_TENANT,
  role: "editor",
  permissions: ["workspace.members.read"],
};

const ME_OWNER_WITH_INVITE: MeResponse = {
  user_id: "u",
  email: "x@x.com",
  platform: null,
  platform_permissions: [],
  tenants: [OWNER_TENANT],
  pending_invite: null,
};

const ME_EDITOR_NO_INVITE: MeResponse = {
  ...ME_OWNER_WITH_INVITE,
  tenants: [EDITOR_TENANT],
};

// A platform admin viewing a client workspace they are NOT a member of: the
// route param slug ("acme") matches no entry in me.tenants. Members + info still
// come from the platform endpoint.
const ME_NON_MEMBER: MeResponse = {
  ...ME_OWNER_WITH_INVITE,
  tenants: [],
};

const CLIENT_DETAIL: PlatformClientDetail = {
  id: "t-1",
  slug: "acme",
  name: "Acme Corp",
  created_at: new Date("2026-01-01T00:00:00Z").toISOString(),
  owner_email: "owner@example.com",
  member_count: 2,
  members: [
    {
      auth_user_id: "m-owner",
      email: "owner@example.com",
      role: "owner",
      joined_at: new Date("2026-01-01T00:00:00Z").toISOString(),
    },
    {
      auth_user_id: "m-editor",
      email: "editor@example.com",
      role: "editor",
      joined_at: new Date("2026-01-02T00:00:00Z").toISOString(),
    },
  ],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantUsersPage />
    </QueryClientProvider>,
  );
}

describe("TenantUsersPage", () => {
  beforeEach(() => {
    vi.mocked(fetchPlatformClient).mockReset();
    vi.mocked(fetchTenantInvites).mockReset();
    vi.mocked(postTenantInvite).mockReset();
    vi.mocked(fetchMe).mockReset();
    vi.mocked(fetchPlatformClient).mockResolvedValue(CLIENT_DETAIL);
    vi.mocked(fetchTenantInvites).mockResolvedValue({ items: [] });
  });

  it("renders the client name and members from the platform endpoint", async () => {
    vi.mocked(fetchMe).mockResolvedValue(ME_OWNER_WITH_INVITE);
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /acme corp — users/i })).toBeInTheDocument(),
    );
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByText("editor@example.com")).toBeInTheDocument();
  });

  it("renders client name + members even when the viewer is NOT a member", async () => {
    vi.mocked(fetchMe).mockResolvedValue(ME_NON_MEMBER);
    renderPage();
    // Members come from the platform endpoint, not from me.tenants.
    await waitFor(() => expect(screen.getByText("owner@example.com")).toBeInTheDocument());
    expect(screen.getByText("editor@example.com")).toBeInTheDocument();
    expect(screen.queryByText(/limited view/i)).toBeNull();
    // A non-member fetches no workspace-scoped invites.
    expect(fetchTenantInvites).not.toHaveBeenCalled();
  });

  it("renders the Invite button when me has workspace.members.invite for this tenant", async () => {
    vi.mocked(fetchMe).mockResolvedValue(ME_OWNER_WITH_INVITE);
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /invite user/i })).toBeInTheDocument(),
    );
  });

  it("does NOT render the Invite button when me lacks workspace.members.invite", async () => {
    vi.mocked(fetchMe).mockResolvedValue(ME_EDITOR_NO_INVITE);
    renderPage();
    await waitFor(() => expect(fetchMe).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /invite user/i })).toBeNull();
  });

  it("invites a user with the default role", async () => {
    vi.mocked(fetchMe).mockResolvedValue(ME_OWNER_WITH_INVITE);
    vi.mocked(postTenantInvite).mockResolvedValue({
      id: "1",
      tenant_id: "t-1",
      email: "ed@example.com",
      role: "admin",
      expires_at: new Date().toISOString(),
      accepted_at: null,
      revoked_at: null,
      created_at: new Date().toISOString(),
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: /invite user/i }));
    await user.click(screen.getByRole("button", { name: /invite user/i }));
    await user.type(screen.getByLabelText(/email/i), "ed@example.com");
    await user.click(screen.getByRole("button", { name: /send invite/i }));
    await waitFor(() =>
      expect(postTenantInvite).toHaveBeenCalledWith("t-1", "ed@example.com", "admin"),
    );
  });
});
