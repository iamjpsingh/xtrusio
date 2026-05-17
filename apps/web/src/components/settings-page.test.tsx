import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SettingsPage } from "./settings-page";

vi.mock("@/lib/api", () => ({
  fetchPlatformSettings: vi.fn(),
  putPlatformSettings: vi.fn(),
}));

import { fetchPlatformSettings, putPlatformSettings } from "@/lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.mocked(fetchPlatformSettings).mockReset();
    vi.mocked(putPlatformSettings).mockReset();
  });

  it("renders the signups toggle and flips it on click", async () => {
    vi.mocked(fetchPlatformSettings).mockResolvedValue({
      signups_enabled: false,
      updated_at: new Date().toISOString(),
      updated_by_email: null,
    });
    vi.mocked(putPlatformSettings).mockResolvedValue({ signups_enabled: true });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole("switch"));
    expect(screen.getByText("Public client signup")).toBeTruthy();
    expect(
      screen.getByText(
        "Allow anyone to create a new client workspace via the public sign-up page.",
      ),
    ).toBeTruthy();
    await user.click(screen.getByRole("switch"));
    await waitFor(() =>
      expect(putPlatformSettings).toHaveBeenCalledWith(true),
    );
  });
});
