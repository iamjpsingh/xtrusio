import { Link, useRouterState } from "@tanstack/react-router";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { SearchTrigger } from "@/components/search-trigger";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { platformNav, workspaceNav } from "@/lib/nav";
import { findTenant, useMe } from "@/lib/me-adapter";

function platformLabel(pathname: string): string {
  if (pathname === "/platform") return "Platform";
  const item = platformNav.find((n) => n.to === pathname);
  return item?.label ?? pathname.replace(/^\/platform\/?/, "");
}

function workspaceLabel(pathname: string, workspaceId: string): string {
  const suffix = pathname.replace(`/workspace/${workspaceId}`, "");
  if (suffix === "" || suffix === "/") return "Overview";
  const item = workspaceNav.find((n) => n.to === suffix);
  return item?.label ?? suffix.replace(/^\//, "");
}

export function AppTopbar() {
  const { location } = useRouterState();
  const { me } = useMe();
  const path = location.pathname;

  let scopeLabel = "Xtrusio";
  let pageLabel = path.replace(/^\//, "");

  if (path === "/platform" || path.startsWith("/platform/")) {
    scopeLabel = "Platform";
    pageLabel = platformLabel(path);
  } else {
    const m = /^\/workspace\/([^/]+)/.exec(path);
    if (m) {
      const wid = m[1] ?? "";
      const t = findTenant(me, wid);
      scopeLabel = t?.name ?? "Workspace";
      pageLabel = workspaceLabel(path, wid);
    }
  }

  return (
    <header className="bg-background sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/">{scopeLabel}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          {pageLabel && pageLabel !== scopeLabel && (
            <>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{pageLabel}</BreadcrumbPage>
              </BreadcrumbItem>
            </>
          )}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="ml-auto flex items-center gap-2">
        <SearchTrigger />
        <Separator orientation="vertical" className="mx-1 h-5" />
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
