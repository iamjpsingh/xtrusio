import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { TenantUsersPage } from "./tenant-users-page";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  fetchTenantInvites: vi.fn(),
  postTenantInvite: vi.fn(),
  deleteTenantInvite: vi.fn(),
  fetchMe: vi.fn(),
}));
vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ slug: "acme" }),
}));

import { fetchMe, fetchTenantInvites, postTenantInvite } from "@/lib/api";

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
    vi.mocked(fetchTenantInvites).mockReset();
    vi.mocked(postTenantInvite).mockReset();
    vi.mocked(fetchMe).mockReset();
  });

  it("invites a user with the default role", async () => {
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u",
      email: "x@x.com",
      platform: null,
      platform_permissions: [],
      tenants: [
        {
          id: "t-1",
          slug: "acme",
          name: "Acme",
          role: "owner",
          permissions: ["workspace.members.read", "workspace.members.manage"],
        },
      ],
      pending_invite: null,
    });
    vi.mocked(fetchTenantInvites).mockResolvedValue({ items: [] });
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
