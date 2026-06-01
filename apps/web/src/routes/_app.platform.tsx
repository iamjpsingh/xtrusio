import { Outlet, createFileRoute } from "@tanstack/react-router";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { PlatformSidebar } from "@/components/platform-sidebar";
import { AppTopbar } from "@/components/app-topbar";
import { PageContainer } from "@/components/page-container";

function PlatformShell() {
  return (
    <SidebarProvider>
      <PlatformSidebar />
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

export const Route = createFileRoute("/_app/platform")({
  component: PlatformShell,
});
