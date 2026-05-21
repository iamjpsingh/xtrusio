import { Link, useRouterState } from "@tanstack/react-router";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { workspaceNav } from "@/lib/nav";
import { findTenant, hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";

export function WorkspaceSidebar({ workspaceId }: { workspaceId: string }) {
  const { location } = useRouterState();
  const { me } = useMe();
  const tenant = findTenant(me, workspaceId);
  const items = workspaceNav.filter((n) => hasWorkspacePerm(me, workspaceId, n.required_perm));
  const base = `/workspace/${workspaceId}`;

  return (
    <Sidebar variant="inset">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-foreground text-background text-xs font-bold">
            {(tenant?.name ?? "?").slice(0, 1).toUpperCase()}
          </div>
          <span className="text-sm font-semibold tracking-tight truncate">
            {tenant?.name ?? "Workspace"}
          </span>
        </div>
        <WorkspaceSwitcher />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => {
                const fullPath = `${base}${item.to}`;
                const active = location.pathname === fullPath;
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={fullPath}>
                    <SidebarMenuButton asChild isActive={active}>
                      <Link to={fullPath}>
                        <Icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  );
}
