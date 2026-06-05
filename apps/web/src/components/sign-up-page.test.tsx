import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SignUpPage } from "./sign-up-page";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  fetchSignupStatus: vi.fn(),
  postSignup: vi.fn(),
  postSignupResend: vi.fn(),
}));

import { ApiError, fetchSignupStatus, postSignup, postSignupResend } from "@/lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SignUpPage />
    </QueryClientProvider>,
  );
}

describe("SignUpPage", () => {
  beforeEach(() => {
    vi.mocked(fetchSignupStatus).mockReset();
    vi.mocked(postSignup).mockReset();
    vi.mocked(postSignupResend).mockReset();
  });

  it("renders disabled message when signups_enabled=false", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: false });
    renderPage();
    await waitFor(() => expect(screen.getByText(/sign-up unavailable/i)).toBeTruthy());
  });

  it("renders form when enabled, submits, shows confirmation screen", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    vi.mocked(postSignup).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText(/email/i));
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.type(screen.getByLabelText("Password"), "Password1!");
    await user.click(screen.getByRole("button", { name: /sign up/i }));
    await waitFor(() => expect(screen.getByText(/check your email/i)).toBeTruthy());
    expect(postSignup).toHaveBeenCalledWith("alice@example.com", "Password1!");
  });

  it("renders a 'Sign in' switch link on the form", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    renderPage();
    const link = await screen.findByRole("link", { name: /^sign in$/i });
    expect(link).toHaveAttribute("href", "/sign-in");
  });

  it("resends the confirmation email and applies a cooldown on the success screen", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    vi.mocked(postSignup).mockResolvedValue(undefined);
    vi.mocked(postSignupResend).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText(/email/i));
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.type(screen.getByLabelText("Password"), "Password1!");
    await user.click(screen.getByRole("button", { name: /sign up/i }));
    await waitFor(() => expect(screen.getByText(/check your email/i)).toBeTruthy());

    const resendBtn = screen.getByRole("button", { name: /resend email/i });
    await user.click(resendBtn);
    expect(postSignupResend).toHaveBeenCalledWith("alice@example.com");
    // After a successful resend the button enters cooldown (disabled + countdown).
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /resend email \(\d+s\)/i });
      expect(btn).toBeDisabled();
    });
  });

  it("maps a known API error code to its friendly message", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    vi.mocked(postSignup).mockRejectedValue(new ApiError(403, { detail: "signups_disabled" }));
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText(/email/i));
    await user.type(screen.getByLabelText(/email/i), "bob@example.com");
    await user.type(screen.getByLabelText("Password"), "Password1!");
    await user.click(screen.getByRole("button", { name: /sign up/i }));
    await waitFor(() =>
      expect(screen.getByText("Signups are currently disabled.")).toBeInTheDocument(),
    );
  });

  it("maps a 429 rate-limit response to the rate-limited message", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    vi.mocked(postSignup).mockRejectedValue(new ApiError(429, { detail: "rate_limited" }));
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText(/email/i));
    await user.type(screen.getByLabelText(/email/i), "bob@example.com");
    await user.type(screen.getByLabelText("Password"), "Password1!");
    await user.click(screen.getByRole("button", { name: /sign up/i }));
    await waitFor(() => expect(screen.getByText(/too many attempts/i)).toBeInTheDocument());
  });
});
