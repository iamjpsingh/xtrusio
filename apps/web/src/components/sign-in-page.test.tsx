import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SignInPage } from "./sign-in-page";

vi.mock("@/lib/api", () => ({ fetchSignupStatus: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ signIn: vi.fn() }) }));
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

import { fetchSignupStatus } from "@/lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SignInPage />
    </QueryClientProvider>,
  );
}

describe("SignInPage", () => {
  beforeEach(() => {
    vi.mocked(fetchSignupStatus).mockReset();
  });

  it("shows the client sign-up link when signups are enabled", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    renderPage();
    const link = await screen.findByRole("link", { name: /public client signup/i });
    expect(link).toHaveAttribute("href", "/sign-up");
  });

  it("hides the link when signups are disabled", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: false });
    renderPage();
    await waitFor(() => expect(fetchSignupStatus).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: /public client signup/i })).toBeNull();
  });

  it("hides the link when the status query errors (fail-closed)", async () => {
    vi.mocked(fetchSignupStatus).mockRejectedValue(new Error("network"));
    renderPage();
    await waitFor(() => expect(fetchSignupStatus).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: /public client signup/i })).toBeNull();
  });
});
