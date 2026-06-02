import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { ForgotPasswordPage } from "./forgot-password-page";

const resetPasswordForEmail = vi.fn();

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { resetPasswordForEmail: (...a: unknown[]) => resetPasswordForEmail(...a) } },
}));
vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

describe("ForgotPasswordPage", () => {
  beforeEach(() => {
    resetPasswordForEmail.mockReset();
  });

  it("submits the email and shows the check-your-email screen (no enumeration)", async () => {
    resetPasswordForEmail.mockResolvedValue({ data: {}, error: null });
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));
    await waitFor(() => expect(screen.getByText(/check your email/i)).toBeInTheDocument());
    expect(resetPasswordForEmail).toHaveBeenCalledWith("alice@example.com", {
      redirectTo: expect.stringContaining("/reset-password"),
    });
  });

  it("surfaces a transport error without revealing account existence", async () => {
    resetPasswordForEmail.mockResolvedValue({
      data: null,
      error: { code: "over_email_send_rate_limit", status: 429 },
    });
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));
    await waitFor(() => expect(screen.getByText(/too many/i)).toBeInTheDocument());
    expect(screen.queryByText(/check your email/i)).toBeNull();
  });

  it("links back to sign in", () => {
    render(<ForgotPasswordPage />);
    const link = screen.getByRole("link", { name: /back to sign in/i });
    expect(link).toHaveAttribute("href", "/sign-in");
  });
});
