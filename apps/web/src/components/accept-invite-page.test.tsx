import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AcceptInvitePage } from "./accept-invite-page";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postAcceptInvite: vi.fn(),
}));
const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}));

import { ApiError, postAcceptInvite } from "@/lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AcceptInvitePage />
    </QueryClientProvider>,
  );
}

describe("AcceptInvitePage", () => {
  beforeEach(() => {
    vi.mocked(postAcceptInvite).mockReset();
    navigateMock.mockReset();
  });

  it("auto-posts on mount and redirects to /", async () => {
    vi.mocked(postAcceptInvite).mockResolvedValue({
      kind: "platform",
      role: "admin",
      tenant_id: null,
    });
    renderPage();
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/" }));
    expect(postAcceptInvite).toHaveBeenCalled();
  });

  it("renders the specific message on a real ApiError", async () => {
    vi.mocked(postAcceptInvite).mockRejectedValue(new ApiError(403, { detail: "invite_expired" }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/this invitation has expired/i)).toBeTruthy());
  });

  it("redirects to / when already provisioned (409)", async () => {
    vi.mocked(postAcceptInvite).mockRejectedValue(
      new ApiError(409, { detail: "already_provisioned" }),
    );
    renderPage();
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/" }));
    expect(screen.queryByText(/couldn.t accept invitation/i)).toBeNull();
  });

  it("renders the accept-invite states inside the shared AuthLayout (Xtrusio wordmark)", async () => {
    vi.mocked(postAcceptInvite).mockResolvedValue({
      kind: "platform",
      role: "admin",
      tenant_id: null,
    });
    renderPage();
    expect(await screen.findByText("Xtrusio")).toBeInTheDocument();
  });
});
