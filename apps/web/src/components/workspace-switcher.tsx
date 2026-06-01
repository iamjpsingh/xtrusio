import { useNavigate, useRouterState } from "@tanstack/react-router";
import { Check, ChevronsUpDown, ShieldCheck, Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useMe } from "@/lib/me-adapter";
import { PLATFORM_SENTINEL, writeLastWorkspace } from "@/lib/last-workspace";
import { cn } from "@/lib/utils";

const PLATFORM_LABEL = "Platform admin";

/** Resolve the scope the current route belongs to: the platform sentinel, a
 * workspace id, or `null` when neither (no item is then checked). */
function activeScope(pathname: string): string | null {
  if (pathname === "/platform" || pathname.startsWith("/platform/")) return PLATFORM_SENTINEL;
  const m = /^\/workspace\/([^/]+)/.exec(pathname);
  return m?.[1] ?? null;
}

export function WorkspaceSwitcher() {
  const navigate = useNavigate();
  const { location } = useRouterState();
  const { me } = useMe();
  if (!me) return null;

  const hasPlatform = me.platform !== null;
  const tenants = me.tenants;
  if (!hasPlatform && tenants.length === 0) return null;

  const scope = activeScope(location.pathname);
  const currentLabel =
    scope === PLATFORM_SENTINEL && hasPlatform
      ? PLATFORM_LABEL
      : (tenants.find((t) => t.id === scope)?.name ?? "Switch workspace");

  const goPlatform = () => {
    writeLastWorkspace(PLATFORM_SENTINEL);
    navigate({ to: "/platform" });
  };

  const goWorkspace = (workspaceId: string) => {
    writeLastWorkspace(workspaceId);
    navigate({ to: "/workspace/$workspaceId", params: { workspaceId } });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          aria-label="Switch workspace"
          className="w-full justify-between gap-2"
        >
          <span className="truncate text-sm">{currentLabel}</span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        {hasPlatform && (
          <>
            <DropdownMenuLabel className="text-muted-foreground text-xs">
              Platform
            </DropdownMenuLabel>
            <DropdownMenuItem onClick={goPlatform} className="gap-2">
              <ShieldCheck className="h-4 w-4" />
              <span>{PLATFORM_LABEL}</span>
              <Check
                className={cn(
                  "ml-auto h-4 w-4",
                  scope === PLATFORM_SENTINEL ? "opacity-100" : "opacity-0",
                )}
                aria-hidden={scope !== PLATFORM_SENTINEL}
              />
            </DropdownMenuItem>
            {tenants.length > 0 && <DropdownMenuSeparator />}
          </>
        )}
        {tenants.length > 0 && (
          <>
            <DropdownMenuLabel className="text-muted-foreground text-xs">
              Workspaces
            </DropdownMenuLabel>
            {tenants.map((t) => (
              <DropdownMenuItem key={t.id} onClick={() => goWorkspace(t.id)} className="gap-2">
                <Building2 className="h-4 w-4" />
                <span className="truncate">{t.name}</span>
                <Check
                  className={cn("ml-auto h-4 w-4", scope === t.id ? "opacity-100" : "opacity-0")}
                  aria-hidden={scope !== t.id}
                />
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
