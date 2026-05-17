import { Outlet, createFileRoute } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { AppTopbar } from "@/components/app-topbar";

export function AppShellLayout({ testChildren }: { testChildren?: ReactNode }) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <AppTopbar />
        <main className="flex-1 p-6">{testChildren ?? <Outlet />}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}

export const Route = createFileRoute("/_app")({
  component: () => <AppShellLayout />,
});
