import { Outlet, createRootRoute, useRouterState } from "@tanstack/react-router";
import { QueryClientProvider } from "@tanstack/react-query";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { AppTopbar } from "@/components/app-topbar";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/lib/auth";
import { AuthGuard } from "@/components/auth-guard";
import { queryClient } from "@/lib/query-client";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const { location } = useRouterState();
  const isAuthRoute = location.pathname === "/sign-in";

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AuthGuard>
            {isAuthRoute ? (
              <main className="min-h-screen bg-background p-6">
                <Outlet />
              </main>
            ) : (
              <SidebarProvider>
                <AppSidebar />
                <SidebarInset>
                  <AppTopbar />
                  <main className="flex-1 p-6">
                    <Outlet />
                  </main>
                </SidebarInset>
              </SidebarProvider>
            )}
            <Toaster richColors closeButton position="bottom-right" />
          </AuthGuard>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
