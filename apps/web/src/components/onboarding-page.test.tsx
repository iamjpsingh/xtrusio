import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { OnboardingPage } from "./onboarding-page";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postOnboarding: vi.fn(),
}));
const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}));

import { ApiError, postOnboarding } from "@/lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OnboardingPage />
    </QueryClientProvider>,
  );
}

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.mocked(postOnboarding).mockReset();
    navigateMock.mockReset();
  });

  it("submits workspace name and navigates to /", async () => {
    vi.mocked(postOnboarding).mockResolvedValue({
      tenant: { id: "t", slug: "acme", name: "Acme", role: "owner" },
    });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(/workspace name/i), "Acme Corp");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/" }));
    expect(postOnboarding).toHaveBeenCalledWith("Acme Corp");
  });

  it("renders inside the shared AuthLayout (Xtrusio wordmark)", () => {
    renderPage();
    expect(screen.getByText("Xtrusio")).toBeInTheDocument();
  });

  it("maps a known onboarding error code to its friendly message", async () => {
    vi.mocked(postOnboarding).mockRejectedValue(
      new ApiError(409, { detail: "already_provisioned" }),
    );
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(/workspace name/i), "Acme Corp");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() =>
      expect(screen.getByText("Your account is already set up.")).toBeInTheDocument(),
    );
  });
});
