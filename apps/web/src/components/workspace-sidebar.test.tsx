import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RouterContextProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { SidebarProvider } from "@/components/ui/sidebar";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { routeTree } from "@/routeTree.gen";

function renderSidebar(workspacePerms: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["me"], {
    user_id: "u",
    email: "x@x.com",
    platform: null,
    platform_permissions: [],
    tenants: [
      {
        id: "t1",
        slug: "acme",
        name: "Acme",
        role: "owner",
        permissions: workspacePerms,
      },
    ],
    pending_invite: null,
  });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/workspace/t1"] }),
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterContextProvider router={router}>
        <SidebarProvider>
          <WorkspaceSidebar workspaceId="t1" />
        </SidebarProvider>
      </RouterContextProvider>
    </QueryClientProvider>,
  );
}

describe("WorkspaceSidebar", () => {
  it("renders Overview + Members when only workspace.members.read is granted", () => {
    renderSidebar(["workspace.members.read"]);
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.queryByText("Roles")).toBeNull();
    expect(screen.queryByText("Audit log")).toBeNull();
  });

  it("renders Audit log when workspace.audit.read is granted", () => {
    renderSidebar(["workspace.members.read", "workspace.audit.read"]);
    expect(screen.getByText("Audit log")).toBeInTheDocument();
  });

  it("renders the workspace name in the header brand block", () => {
    renderSidebar(["workspace.members.read"]);
    // "Acme" now appears in three places (header brand block, the
    // workspace-switcher trigger, and the footer caption — the latter as
    // "Acme · Workspace"). Assert the dedicated brand block in the header:
    // it's the element rendering "Acme" exactly, and NOT the switch-workspace
    // trigger button.
    const header = document.querySelector('[data-slot="sidebar-header"]') as HTMLElement;
    expect(header).not.toBeNull();
    const brand = within(header)
      .getAllByText("Acme")
      .find((el) => el.closest('[aria-label="Switch workspace"]') === null);
    expect(brand).toBeDefined();
    expect(brand).toBeInTheDocument();
  });
});
