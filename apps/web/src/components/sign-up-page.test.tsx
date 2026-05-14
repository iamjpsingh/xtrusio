import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SignUpPage } from "./sign-up-page";

vi.mock("@/lib/api", () => ({
  fetchSignupStatus: vi.fn(),
  postSignup: vi.fn(),
}));

import { fetchSignupStatus, postSignup } from "@/lib/api";

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
  });

  it("renders disabled message when signups_enabled=false", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: false });
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/signups are currently disabled/i)).toBeTruthy(),
    );
  });

  it("renders form when enabled, submits, shows confirmation screen", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    vi.mocked(postSignup).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText(/email/i));
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.type(screen.getByLabelText(/password/i), "Password1!");
    await user.click(screen.getByRole("button", { name: /sign up/i }));
    await waitFor(() => expect(screen.getByText(/check your email/i)).toBeTruthy());
    expect(postSignup).toHaveBeenCalledWith("alice@example.com", "Password1!");
  });
});
