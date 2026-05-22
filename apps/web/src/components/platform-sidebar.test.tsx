import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { SidebarProvider } from "@/components/ui/sidebar";
import { PlatformSidebar } from "@/components/platform-sidebar";
import { routeTree } from "@/routeTree.gen";

function renderSidebar(me: { platform_permissions: string[] }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["me"], {
    user_id: "u",
    email: "x@x.com",
    platform: { role: "admin", is_active: true },
    platform_permissions: me.platform_permissions,
    tenants: [],
    pending_invite: null,
  });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/platform"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <SidebarProvider>
          <PlatformSidebar />
        </SidebarProvider>
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("PlatformSidebar", () => {
  it("renders only Dashboard + Users when only platform.users.read is granted", () => {
    renderSidebar({ platform_permissions: ["platform.users.read"] });
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Users")).toBeInTheDocument();
    expect(screen.queryByText("Clients")).toBeNull();
    expect(screen.queryByText("Settings")).toBeNull();
  });

  it("renders Settings when platform.settings.read is granted", () => {
    renderSidebar({
      platform_permissions: ["platform.users.read", "platform.settings.read"],
    });
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });
});
