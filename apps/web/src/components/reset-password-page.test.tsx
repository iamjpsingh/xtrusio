import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResetPasswordPage } from "./reset-password-page";

const setSession = vi.fn();
const updateUser = vi.fn();
const signOut = vi.fn();
const navigate = vi.fn();

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      setSession: (...a: unknown[]) => setSession(...a),
      updateUser: (...a: unknown[]) => updateUser(...a),
      signOut: (...a: unknown[]) => signOut(...a),
    },
  },
}));
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
  Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

function setHash(hash: string) {
  window.history.replaceState(null, "", `/reset-password${hash}`);
}

describe("ResetPasswordPage", () => {
  beforeEach(() => {
    setSession.mockReset();
    updateUser.mockReset();
    signOut.mockReset();
    navigate.mockReset();
  });
  afterEach(() => {
    setHash("");
  });

  it("establishes the recovery session, accepts a new password, then redirects", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=recovery");
    setSession.mockResolvedValue({ data: {}, error: null });
    updateUser.mockResolvedValue({ data: {}, error: null });
    signOut.mockResolvedValue({ error: null });
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await waitFor(() =>
      expect(setSession).toHaveBeenCalledWith({
        access_token: "at123",
        refresh_token: "rt456",
      }),
    );
    const pwd = await screen.findByLabelText("New password");
    await user.type(pwd, "brandnewpass1");
    await user.type(screen.getByLabelText(/confirm new password/i), "brandnewpass1");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => expect(updateUser).toHaveBeenCalledWith({ password: "brandnewpass1" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: "/sign-in" }));
  });

  it("blocks submit when the two passwords don't match", async () => {
    setHash("#access_token=at123&refresh_token=rt456&type=recovery");
    setSession.mockResolvedValue({ data: {}, error: null });
    const user = userEvent.setup();
    render(<ResetPasswordPage />);
    await screen.findByLabelText("New password");
    await user.type(screen.getByLabelText("New password"), "brandnewpass1");
    await user.type(screen.getByLabelText(/confirm new password/i), "different1");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(await screen.findByText(/passwords don't match/i)).toBeInTheDocument();
    expect(updateUser).not.toHaveBeenCalled();
  });

  it("shows the expired state when the hash carries an error_code", async () => {
    setHash("#error=access_denied&error_code=otp_expired&error_description=expired");
    render(<ResetPasswordPage />);
    await waitFor(() => expect(screen.getByText(/link expired/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /request a new link/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(setSession).not.toHaveBeenCalled();
  });

  it("shows the expired state when there is no recovery payload at all", async () => {
    setHash("");
    render(<ResetPasswordPage />);
    await waitFor(() => expect(screen.getByText(/link expired/i)).toBeInTheDocument());
  });
});
