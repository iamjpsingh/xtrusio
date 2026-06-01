import { Link, useRouterState } from "@tanstack/react-router";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { groupNav, isNavItemActive, workspaceNav } from "@/lib/nav";
import { findTenant, hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";

export function WorkspaceSidebar({ workspaceId }: { workspaceId: string }) {
  const { location } = useRouterState();
  const { me } = useMe();
  const tenant = findTenant(me, workspaceId);
  const items = workspaceNav.filter((n) => hasWorkspacePerm(me, workspaceId, n.required_perm));
  const sections = groupNav(items);
  const base = `/workspace/${workspaceId}`;

  return (
    <Sidebar variant="inset">
      <SidebarHeader className="gap-2.5">
        <div className="flex items-center gap-2 px-1 py-1">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-foreground text-sm font-bold text-background">
            {(tenant?.name ?? "?").slice(0, 1).toUpperCase()}
          </div>
          <span className="truncate text-sm font-semibold tracking-tight">
            {tenant?.name ?? "Workspace"}
          </span>
        </div>
        <WorkspaceSwitcher />
      </SidebarHeader>
      <SidebarContent>
        {sections.map((section) => (
          <SidebarGroup key={section.group}>
            {section.label ? <SidebarGroupLabel>{section.label}</SidebarGroupLabel> : null}
            <SidebarGroupContent>
              <SidebarMenu>
                {section.items.map((item) => {
                  const fullPath = `${base}${item.to}`;
                  const active = isNavItemActive(location.pathname, fullPath, item.to === "");
                  const Icon = item.icon;
                  return (
                    <SidebarMenuItem key={fullPath}>
                      <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
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
        ))}
      </SidebarContent>
      <SidebarFooter>
        <p className="truncate px-2 text-xs text-sidebar-foreground/50 group-data-[collapsible=icon]:hidden">
          {tenant?.name ?? "Workspace"} · Workspace
        </p>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
