import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SignInPage } from "./sign-in-page";
import type { SignInResult } from "@/lib/auth";

const signInMock = vi.fn<(email: string, password: string) => Promise<SignInResult>>();

vi.mock("@/lib/api", () => ({ fetchSignupStatus: vi.fn(), postSignupResend: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ signIn: signInMock }) }));
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

import { fetchSignupStatus, postSignupResend } from "@/lib/api";

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
    vi.mocked(postSignupResend).mockReset();
    signInMock.mockReset();
  });

  it("shows the 'Create an account' link when signups are enabled", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    renderPage();
    const link = await screen.findByRole("link", { name: /create an account/i });
    expect(link).toHaveAttribute("href", "/sign-up");
  });

  it("hides the sign-up link and shows invite copy when signups are disabled", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: false });
    renderPage();
    // The footer is gated on the query resolving — wait for the invite copy to
    // land (it isn't rendered during the loading window).
    expect(await screen.findByText(/have an invite\?/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /create an account/i })).toBeNull();
  });

  it("does not render footer copy until signup-status resolves (no flicker)", async () => {
    // Hold the query in-flight so we can observe the loading window: neither the
    // invite line nor the create-account link should appear while pending.
    let resolve: (v: { signups_enabled: boolean }) => void = () => {};
    vi.mocked(fetchSignupStatus).mockReturnValue(
      new Promise<{ signups_enabled: boolean }>((r) => {
        resolve = r;
      }),
    );
    renderPage();

    // While loading: no footer copy at all (the slot is a neutral &nbsp;).
    expect(screen.queryByText(/have an invite\?/i)).toBeNull();
    expect(screen.queryByRole("link", { name: /create an account/i })).toBeNull();

    // Resolving with signups enabled → the correct copy lands, never the invite line.
    resolve({ signups_enabled: true });
    const link = await screen.findByRole("link", { name: /create an account/i });
    expect(link).toHaveAttribute("href", "/sign-up");
    expect(screen.queryByText(/have an invite\?/i)).toBeNull();
  });

  it("renders a 'Forgot password?' link to /forgot-password", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    renderPage();
    const link = await screen.findByRole("link", { name: /forgot password\?/i });
    expect(link).toHaveAttribute("href", "/forgot-password");
  });

  it("shows a generic message for invalid credentials (no enumeration)", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    signInMock.mockResolvedValue({
      error: "Invalid login credentials",
      code: "invalid_credentials",
      status: 400,
    });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.type(screen.getByLabelText("Password"), "wrongpass1");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(screen.getByText("Email or password is incorrect.")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /resend verification email/i })).toBeNull();
  });

  it("offers a resend-verification button on email_not_confirmed and calls postSignupResend", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    vi.mocked(postSignupResend).mockResolvedValue(undefined);
    signInMock.mockResolvedValue({
      error: "Email not confirmed",
      code: "email_not_confirmed",
      status: 400,
    });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(/email/i), "unconfirmed@example.com");
    await user.type(screen.getByLabelText("Password"), "correcthorse");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    const resendBtn = await screen.findByRole("button", {
      name: /resend verification email/i,
    });
    await user.click(resendBtn);
    expect(postSignupResend).toHaveBeenCalledWith("unconfirmed@example.com");
    await waitFor(() => expect(screen.getByText(/verification email sent/i)).toBeInTheDocument());
  });
});
