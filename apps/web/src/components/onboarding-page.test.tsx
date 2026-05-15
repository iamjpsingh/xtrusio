import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { OnboardingPage } from "./onboarding-page";

vi.mock("@/lib/api", () => ({ postOnboarding: vi.fn() }));
const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}));

import { postOnboarding } from "@/lib/api";

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.mocked(postOnboarding).mockReset();
    navigateMock.mockReset();
  });

  it("submits workspace name and navigates to /", async () => {
    vi.mocked(postOnboarding).mockResolvedValue({
      tenant: { id: "t", slug: "acme", name: "Acme", role: "owner" },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <OnboardingPage />
      </QueryClientProvider>,
    );
    await user.type(screen.getByLabelText(/workspace name/i), "Acme Corp");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/" }));
    expect(postOnboarding).toHaveBeenCalledWith("Acme Corp");
  });
});
