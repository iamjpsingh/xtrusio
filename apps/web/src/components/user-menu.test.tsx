import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse } from "@xtrusio/api-types";
import { UserMenu } from "./user-menu";

const ME: MeResponse = {
  user_id: "u-1",
  email: "super@xtrusio.com",
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.users.read"],
  tenants: [],
  pending_invite: null,
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, fetchMe: vi.fn() };
});

const signOut = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ user: { email: "super@xtrusio.com" }, signOut }),
}));

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
});

function renderWith(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <UserMenu />
    </QueryClientProvider>,
  );
}

describe("<UserMenu />", () => {
  it("renders the email and the platform-role badge from useMe()", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await userEvent.click(screen.getByRole("button", { name: /user menu/i }));
    await waitFor(() => {
      expect(screen.getByText("super@xtrusio.com")).toBeInTheDocument();
      expect(screen.getByText(/super admin/i)).toBeInTheDocument();
    });
  });

  it("renders without a Badge when me.platform is null", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue({
      ...ME,
      platform: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await userEvent.click(screen.getByRole("button", { name: /user menu/i }));
    await waitFor(() => expect(screen.getByText("super@xtrusio.com")).toBeInTheDocument());
    expect(screen.queryByText(/super admin|^admin$|^editor$/i)).toBeNull();
  });

  it("fires signOut on click", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await userEvent.click(screen.getByRole("button", { name: /user menu/i }));
    await userEvent.click(screen.getByText(/sign out/i));
    expect(signOut).toHaveBeenCalled();
  });
});
