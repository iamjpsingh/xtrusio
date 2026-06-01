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
import { groupNav, isNavItemActive, platformNav } from "@/lib/nav";
import { hasPlatformPerm, useMe } from "@/lib/me-adapter";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";

export function PlatformSidebar() {
  const { location } = useRouterState();
  const { me } = useMe();
  const items = platformNav.filter((n) => hasPlatformPerm(me, n.required_perm));
  const sections = groupNav(items);

  return (
    <Sidebar variant="inset">
      <SidebarHeader className="gap-2.5">
        <div className="flex items-center gap-2 px-1 py-1">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-foreground text-sm font-bold text-background">
            X
          </div>
          <span className="text-sm font-semibold tracking-tight">Xtrusio</span>
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
                  const Icon = item.icon;
                  const active = isNavItemActive(
                    location.pathname,
                    item.to,
                    item.to === "/platform",
                  );
                  return (
                    <SidebarMenuItem key={item.to}>
                      <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
                        <Link to={item.to}>
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
        <p className="px-2 text-xs text-sidebar-foreground/50 group-data-[collapsible=icon]:hidden">
          Xtrusio · Platform
        </p>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
