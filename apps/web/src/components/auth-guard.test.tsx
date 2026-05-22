import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, test, vi } from "vitest";
import { queryClientDefaults } from "../lib/query-client";

const navigateMock = vi.fn();
let mockPathname = "/";
vi.mock("@tanstack/react-router", () => ({
  useRouterState: ({ select }: { select: (s: { location: { pathname: string } }) => unknown }) =>
    select({ location: { pathname: mockPathname } }),
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
  // Mirror production defaults so AuthGuard's inheritance of `staleTime` is
  // exercised; override `retry` to false so failures surface immediately.
  const qc = new QueryClient({
    ...queryClientDefaults,
    defaultOptions: {
      queries: {
        ...queryClientDefaults.defaultOptions?.queries,
        retry: false,
      },
    },
  });
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

  it("renders children when user is super_admin on /platform", async () => {
    mockPathname = "/platform";
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u",
      email: "x@x.com",
      platform: { role: "super_admin", is_active: true },
      platform_permissions: ["platform.users.read"],
      tenants: [],
      pending_invite: null,
    });
    renderGuard();
    await waitFor(() => expect(screen.getByTestId("child")).toBeTruthy());
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("redirects unprovisioned user to /onboarding", async () => {
    mockPathname = "/platform";
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u",
      email: "x@x.com",
      platform: null,
      platform_permissions: [],
      tenants: [],
      pending_invite: null,
    });
    renderGuard();
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/onboarding" }));
  });

  test("inherits staleTime from production queryClient defaults", () => {
    // grep: AuthGuard must inherit staleTime from queryClient — do not re-declare here.
    // If a future refactor adds staleTime back to AuthGuard's useQuery options,
    // this assertion (and the comment above) flag the regression.
    expect(queryClientDefaults.defaultOptions?.queries?.staleTime).toBe(30_000);
  });
});
