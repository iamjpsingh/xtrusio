import { render, screen } from "@testing-library/react";
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

  it("renders the workspace name in the header", () => {
    renderSidebar(["workspace.members.read"]);
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });
});
