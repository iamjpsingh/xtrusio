import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { UsersPage } from "./users-page";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  fetchPlatformInvites: vi.fn(),
  postPlatformInvite: vi.fn(),
  deletePlatformInvite: vi.fn(),
}));

import { deletePlatformInvite, fetchPlatformInvites, postPlatformInvite } from "@/lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UsersPage />
    </QueryClientProvider>,
  );
}

describe("UsersPage", () => {
  beforeEach(() => {
    vi.mocked(fetchPlatformInvites).mockReset();
    vi.mocked(postPlatformInvite).mockReset();
    vi.mocked(deletePlatformInvite).mockReset();
  });

  it("renders pending invites and lets super_admin invite a new user", async () => {
    vi.mocked(fetchPlatformInvites).mockResolvedValue({ items: [] });
    vi.mocked(postPlatformInvite).mockResolvedValue({
      id: "1",
      email: "alice@example.com",
      role: "admin",
      expires_at: new Date().toISOString(),
      accepted_at: null,
      revoked_at: null,
      created_at: new Date().toISOString(),
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /invite user/i }));
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.click(screen.getByRole("button", { name: /send invite/i }));
    await waitFor(() =>
      expect(postPlatformInvite).toHaveBeenCalledWith("alice@example.com", "admin"),
    );
  });
});
