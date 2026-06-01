import { Outlet, createFileRoute, useParams } from "@tanstack/react-router";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { AppTopbar } from "@/components/app-topbar";
import { PageContainer } from "@/components/page-container";

function WorkspaceShell() {
  const { workspaceId } = useParams({ from: "/_app/workspace/$workspaceId" });
  return (
    <SidebarProvider>
      <WorkspaceSidebar workspaceId={workspaceId} />
      <SidebarInset>
        <AppTopbar />
        <main className="flex-1 p-6">
          <PageContainer>
            <Outlet />
          </PageContainer>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}

export const Route = createFileRoute("/_app/workspace/$workspaceId")({
  component: WorkspaceShell,
});
