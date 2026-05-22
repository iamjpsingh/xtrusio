import { useNavigate } from "@tanstack/react-router";
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

export function WorkspaceSwitcher() {
  const navigate = useNavigate();
  const { me } = useMe();
  if (!me) return null;

  const hasPlatform = me.platform !== null;
  const tenants = me.tenants;
  if (!hasPlatform && tenants.length === 0) return null;

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
          <span className="truncate text-sm">Switch workspace</span>
          <ChevronsUpDown className="h-4 w-4 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        {hasPlatform && (
          <>
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Platform
            </DropdownMenuLabel>
            <DropdownMenuItem onClick={goPlatform} className="gap-2">
              <ShieldCheck className="h-4 w-4" />
              <span>Platform admin</span>
              <Check className="ml-auto h-4 w-4 opacity-0" />
            </DropdownMenuItem>
            {tenants.length > 0 && <DropdownMenuSeparator />}
          </>
        )}
        {tenants.length > 0 && (
          <>
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Workspaces
            </DropdownMenuLabel>
            {tenants.map((t) => (
              <DropdownMenuItem key={t.id} onClick={() => goWorkspace(t.id)} className="gap-2">
                <Building2 className="h-4 w-4" />
                <span className="truncate">{t.name}</span>
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
