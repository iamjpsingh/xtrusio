import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse } from "@xtrusio/api-types";
import { routeTree } from "@/routeTree.gen";
import { SidebarProvider } from "@/components/ui/sidebar";
import { AppTopbar } from "./app-topbar";

const ME: MeResponse = {
  user_id: "u1",
  email: "admin@example.com",
  platform: { role: "admin", is_active: true },
  platform_permissions: [],
  tenants: [],
  pending_invite: null,
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, fetchMe: vi.fn() };
});

import * as api from "@/lib/api";

const mockedMe = vi.mocked(api.fetchMe);

beforeEach(() => {
  vi.clearAllMocks();
  mockedMe.mockResolvedValue(ME);
});

function renderTopbar(initial = "/platform") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initial] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <SidebarProvider>
          <AppTopbar />
        </SidebarProvider>
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("<AppTopbar /> breadcrumb home link", () => {
  it("renders the home crumb as a client TanStack Link (not a full-reload anchor)", () => {
    renderTopbar("/platform");
    const link = screen.getByRole("link", { name: "Platform" });
    // TanStack Link still renders an <a href="/"> for accessibility / new-tab,
    // but it is the routed slot, not a bare native anchor.
    expect(link.tagName).toBe("A");
    expect(link).toHaveAttribute("href", "/");
    expect(link).toHaveAttribute("data-slot", "breadcrumb-link");
  });

  it("intercepts a plain left-click (preventDefault) so there is no browser reload", () => {
    renderTopbar("/platform");
    const link = screen.getByRole("link", { name: "Platform" });
    // A native <a href="/"> click would NOT be defaultPrevented (full reload).
    // TanStack Link's onClick calls preventDefault for in-app navigation.
    const clickEvent = new MouseEvent("click", { bubbles: true, cancelable: true });
    fireEvent(link, clickEvent);
    expect(clickEvent.defaultPrevented).toBe(true);
  });
});
