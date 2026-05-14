import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useRouter: () => ({ state: { location: { pathname: "/" } } }),
  useNavigate: () => navigateMock,
}));

vi.mock("../lib/api", () => ({
  fetchMe: vi.fn(),
}));

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ session: "fake-session", loading: false }),
}));

import { fetchMe } from "../lib/api";
import { AuthGuard } from "./auth-guard";

function renderGuard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AuthGuard>
        <div data-testid="child">inner</div>
      </AuthGuard>
    </QueryClientProvider>,
  );
}

describe("AuthGuard", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    vi.mocked(fetchMe).mockReset();
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders children when user is super_admin on /", async () => {
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u",
      email: "x@x.com",
      platform: { role: "super_admin", is_active: true },
      tenants: [],
      pending_invite: null,
    });
    renderGuard();
    await waitFor(() => expect(screen.getByTestId("child")).toBeTruthy());
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("redirects unprovisioned user to /onboarding", async () => {
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u",
      email: "x@x.com",
      platform: null,
      tenants: [],
      pending_invite: null,
    });
    renderGuard();
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith({ to: "/onboarding" }),
    );
  });
});
